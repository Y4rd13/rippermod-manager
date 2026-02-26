"""Abstract archive handler with implementations for ZIP, 7z, and RAR.

Provides a uniform interface for listing and extracting files from
mod archives regardless of format.
"""

from __future__ import annotations

import tempfile
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".zip", ".7z", ".rar"}


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    filename: str
    is_dir: bool
    size: int = 0


class ArchiveHandler(ABC):
    """Base class for archive format handlers."""

    @abstractmethod
    def list_entries(self) -> list[ArchiveEntry]:
        """Return all entries in the archive."""

    @abstractmethod
    def read_file(self, entry: ArchiveEntry) -> bytes:
        """Read the contents of a single file entry."""

    def read_all_files(self, entries: list[ArchiveEntry]) -> dict[str, bytes]:
        """Read all file entries in a single pass. Override for efficiency."""
        return {e.filename: self.read_file(e) for e in entries if not e.is_dir}

    @abstractmethod
    def close(self) -> None:
        """Release resources."""

    def __enter__(self) -> ArchiveHandler:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


class ZipHandler(ArchiveHandler):
    """Handler for .zip archives using stdlib zipfile."""

    def __init__(self, path: str | Path) -> None:
        self._zf = zipfile.ZipFile(path, "r")

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for info in self._zf.infolist():
            entries.append(
                ArchiveEntry(
                    filename=info.filename,
                    is_dir=info.is_dir(),
                    size=info.file_size,
                )
            )
        return entries

    def read_file(self, entry: ArchiveEntry) -> bytes:
        return self._zf.read(entry.filename)

    def close(self) -> None:
        self._zf.close()


class SevenZipHandler(ArchiveHandler):
    """Handler for .7z archives using py7zr.

    py7zr >= 1.0 removed the ``read()`` method.  All extraction now goes
    through ``extract(path, targets)`` which writes to disk, so we use a
    temporary directory for in-memory reads.
    """

    def __init__(self, path: str | Path) -> None:
        try:
            import py7zr
        except ImportError as exc:
            raise ImportError("py7zr is required for .7z support: pip install py7zr") from exc
        self._path = Path(path)
        self._archive = py7zr.SevenZipFile(self._path, mode="r")
        self._cache: dict[str, bytes] | None = None

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for entry in self._archive.list():
            entries.append(
                ArchiveEntry(
                    filename=entry.filename,
                    is_dir=entry.is_directory,
                    size=entry.uncompressed if hasattr(entry, "uncompressed") else 0,
                )
            )
        return entries

    def _extract_to_bytes(self, targets: list[str]) -> dict[str, bytes]:
        """Extract *targets* to a temp dir and return their contents as bytes."""
        self._archive.reset()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir).resolve()
            self._archive.extract(path=tmpdir, targets=targets)
            result: dict[str, bytes] = {}
            for name in targets:
                extracted = (tmpdir_path / name).resolve()
                if extracted.is_file() and tmpdir_path in extracted.parents:
                    result[name] = extracted.read_bytes()
        return result

    def read_file(self, entry: ArchiveEntry) -> bytes:
        if self._cache is not None and entry.filename in self._cache:
            return self._cache[entry.filename]
        data = self._extract_to_bytes([entry.filename])
        return data.get(entry.filename, b"")

    def read_all_files(self, entries: list[ArchiveEntry]) -> dict[str, bytes]:
        """Read all files in a single pass, avoiding O(N²) resets."""
        targets = [e.filename for e in entries if not e.is_dir]
        result = self._extract_to_bytes(targets)
        self._cache = result
        return result

    def close(self) -> None:
        self._cache = None
        self._archive.close()


class RarHandler(ArchiveHandler):
    """Handler for .rar archives using the rarfile library."""

    def __init__(self, path: str | Path) -> None:
        try:
            import rarfile
        except ImportError as exc:
            raise ImportError(
                "rarfile is required for .rar support: pip install rarfile"
            ) from exc
        self._rf = rarfile.RarFile(str(path), "r")

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for info in self._rf.infolist():
            entries.append(
                ArchiveEntry(
                    filename=info.filename,
                    is_dir=info.is_dir(),
                    size=info.file_size,
                )
            )
        return entries

    def read_file(self, entry: ArchiveEntry) -> bytes:
        return self._rf.read(entry.filename)

    def close(self) -> None:
        self._rf.close()


def open_archive(path: str | Path) -> ArchiveHandler:
    """Open an archive file and return the appropriate handler.

    Raises:
        ValueError: If the file extension is not supported.
        zipfile.BadZipFile: If a ZIP file is corrupt.
    """
    path = Path(path)
    ext = path.suffix.lower()

    if ext == ".zip":
        return ZipHandler(path)
    if ext == ".7z":
        return SevenZipHandler(path)
    if ext == ".rar":
        return RarHandler(path)

    raise ValueError(f"Unsupported archive format: {ext}")
