"""Low-level VFS primitives: hardlinks, junctions, probes."""

from __future__ import annotations

import os
from pathlib import Path


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


def junction(target: Path, link: Path) -> None:
    """Create an NTFS directory junction at `link` pointing to `target`."""
    raise NotImplementedError


def remove_junction(link: Path) -> None:
    """Remove a junction reparse point. Idempotent."""
    raise NotImplementedError


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
    raise NotImplementedError


def is_game_running(exe_name: str = "Cyberpunk2077.exe") -> bool:
    """Return True iff a process with the given exe name is running."""
    raise NotImplementedError
