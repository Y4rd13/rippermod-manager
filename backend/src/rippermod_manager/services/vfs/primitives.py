"""Low-level VFS primitives: hardlinks, junctions, probes."""

from __future__ import annotations

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
    raise NotImplementedError


def unlink(dst: Path) -> None:
    """Remove a hardlink or regular file at dst. No-op if absent."""
    raise NotImplementedError


def junction(target: Path, link: Path) -> None:
    """Create an NTFS directory junction at `link` pointing to `target`."""
    raise NotImplementedError


def remove_junction(link: Path) -> None:
    """Remove a junction reparse point. Idempotent."""
    raise NotImplementedError


def verify_link(src: Path, dst: Path) -> bool:
    """Return True iff dst is a hardlink (same inode) to src."""
    raise NotImplementedError


def same_volume(a: Path, b: Path) -> bool:
    """Return True iff a and b live on the same NTFS volume."""
    raise NotImplementedError


def probe_hardlink_support(staging_dir: Path, target_dir: Path) -> bool:
    """Canary: write tmp file in staging_dir, hardlink into target_dir, cleanup."""
    raise NotImplementedError


def is_game_running(exe_name: str = "Cyberpunk2077.exe") -> bool:
    """Return True iff a process with the given exe name is running."""
    raise NotImplementedError
