"""Low-level VFS primitives: hardlinks, junctions, probes."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import psutil


class VfsError(Exception):
    """Base class for VFS-specific failures."""


class CrossVolumeError(VfsError):
    pass


class AlreadyExistsError(VfsError):
    pass


class NotFoundError(VfsError):
    pass


class PermissionDeniedError(VfsError):
    pass


class FilesystemUnsupportedError(VfsError):
    pass


class GameRunningError(VfsError):
    pass


def hardlink(src: Path, dst: Path) -> None:
    """Create a hardlink at dst pointing to src. Raises VfsError on failure."""
    if not src.exists():
        raise NotFoundError(f"source missing: {src}")
    if dst.exists():
        raise AlreadyExistsError(f"destination exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except FileExistsError as exc:
        raise AlreadyExistsError(str(exc)) from exc
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except OSError as exc:
        if getattr(exc, "winerror", None) == 17:  # ERROR_NOT_SAME_DEVICE
            raise CrossVolumeError(f"{src} and {dst} are not on the same volume") from exc
        if getattr(exc, "winerror", None) == 1 or "not supported" in str(exc).lower():
            raise FilesystemUnsupportedError(str(exc)) from exc
        if getattr(exc, "winerror", None) == 5:
            raise PermissionDeniedError(str(exc)) from exc
        raise VfsError(str(exc)) from exc


def unlink(dst: Path) -> None:
    """Remove a hardlink or regular file at dst. No-op if absent."""
    try:
        dst.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise VfsError(str(exc)) from exc


# cmd.exe metacharacters that can break out of even a quoted argument. We pass
# the args as a list with shell=False, but cmd.exe still parses these in its own
# arg-handling layer. Reject paths containing them.
_CMD_FORBIDDEN = re.compile(r'[&|<>^"%!\r\n]')


def junction(target: Path, link: Path) -> None:
    """Create an NTFS directory junction at `link` pointing to `target`.

    Rejects paths containing cmd.exe metacharacters (``& | < > ^ " % !`` or newlines)
    even though we invoke cmd with ``shell=False``: cmd.exe parses its own arg list and
    these characters can still break out of quoting. Mod paths that originate from
    untrusted archives must be validated here.
    """
    if not target.is_dir():
        raise NotFoundError(f"junction target must be an existing directory: {target}")
    if link.exists():
        raise AlreadyExistsError(f"junction link path exists: {link}")
    target_str = str(target)
    link_str = str(link)
    if _CMD_FORBIDDEN.search(target_str) or _CMD_FORBIDDEN.search(link_str):
        raise VfsError(
            'junction path contains characters unsafe for cmd.exe (& | < > ^ " % !): '
            f"target={target_str!r}, link={link_str!r}"
        )
    link.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", link_str, target_str],
        capture_output=True,
        text=True,
        shell=False,
        timeout=10,
    )
    if proc.returncode != 0:
        raise VfsError(f"mklink /J failed: {proc.stderr.strip() or proc.stdout.strip()}")


def remove_junction(link: Path) -> None:
    """Remove a junction reparse point. Idempotent."""
    if not link.exists():
        return
    try:
        os.rmdir(link)
    except OSError as exc:
        raise VfsError(f"could not remove junction {link}: {exc}") from exc


def verify_link(src: Path, dst: Path) -> bool:
    """Return True iff dst is a hardlink (same inode) to src."""
    try:
        return os.path.samefile(src, dst)
    except (FileNotFoundError, OSError):
        return False


def _existing_ancestor(p: Path) -> Path:
    """Walk up until we find a path that exists. Used by same_volume for non-existent paths."""
    p = p.resolve(strict=False)
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def same_volume(a: Path, b: Path) -> bool:
    """Return True iff a and b live on the same NTFS volume."""
    try:
        sa = os.stat(_existing_ancestor(a))
        sb = os.stat(_existing_ancestor(b))
        return sa.st_dev == sb.st_dev
    except OSError as exc:
        raise VfsError(str(exc)) from exc


def probe_hardlink_support(staging_dir: Path, target_dir: Path) -> bool:
    """Canary: write tmp file in staging_dir, hardlink into target_dir, cleanup."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    canary = staging_dir / ".rmm_canary.tmp"
    link = target_dir / ".rmm_canary.link"
    try:
        canary.write_bytes(b"x")
        try:
            os.link(canary, link)
        except OSError:
            return False
        return True
    finally:
        link.unlink(missing_ok=True)
        canary.unlink(missing_ok=True)


def is_game_running(exe_name: str = "Cyberpunk2077.exe") -> bool:
    """Return True iff a process with the given exe name is running."""
    needle = exe_name.lower()
    for proc in psutil.process_iter(attrs=["name"]):
        name = (proc.info.get("name") or "").lower()
        if name == needle:
            return True
    return False
