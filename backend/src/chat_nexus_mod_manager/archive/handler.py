"""Abstract archive handler with implementations for ZIP, 7z, and RAR.

Provides a uniform interface for listing and extracting files from
mod archives regardless of format.
"""

from __future__ import annotations

import io
import shutil
import subprocess
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
    """Handler for .7z archives using py7zr."""

    def __init__(self, path: str | Path) -> None:
        try:
            import py7zr
        except ImportError as exc:
            raise ImportError("py7zr is required for .7z support: pip install py7zr") from exc
        self._path = Path(path)
        self._archive = py7zr.SevenZipFile(self._path, mode="r")

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

    def read_file(self, entry: ArchiveEntry) -> bytes:
        self._archive.reset()
        result = self._archive.read(targets=[entry.filename])
        if result and entry.filename in result:
            bio = result[entry.filename]
            if isinstance(bio, io.BytesIO):
                return bio.read()
            return bytes(bio)
        return b""

    def close(self) -> None:
        self._archive.close()


def _find_7zip() -> str | None:
    """Locate the 7-Zip CLI executable."""
    common = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for p in common:
        if Path(p).exists():
            return p
    return shutil.which("7z")


class RarHandler(ArchiveHandler):
    """Handler for .rar archives using 7-Zip CLI.

    RAR extraction requires 7-Zip to be installed on the system.
    """

    def __init__(self, path: str | Path) -> None:
        self._exe = _find_7zip()
        if not self._exe:
            raise FileNotFoundError(
                "RAR extraction requires 7-Zip. Install via: winget install 7zip.7zip"
            )
        self._path = str(path)
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None

    def list_entries(self) -> list[ArchiveEntry]:
        result = subprocess.run(
            [self._exe, "l", "-slt", self._path],  # type: ignore[list-item]
            capture_output=True,
            text=True,
            timeout=60,
        )
        entries: list[ArchiveEntry] = []
        current_path = ""
        current_size = 0
        current_is_dir = False

        for line in result.stdout.splitlines():
            line = line.strip()
            if (line.startswith("Path = ") and entries) or current_path:
                if current_path:
                    entries.append(
                        ArchiveEntry(
                            filename=current_path,
                            is_dir=current_is_dir,
                            size=current_size,
                        )
                    )
                current_path = line[7:]
                current_size = 0
                current_is_dir = False
            elif line.startswith("Path = "):
                current_path = line[7:]
            elif line.startswith("Size = "):
                try:
                    current_size = int(line[7:])
                except ValueError:
                    current_size = 0
            elif line.startswith("Folder = +"):
                current_is_dir = True

        if current_path:
            entries.append(
                ArchiveEntry(
                    filename=current_path,
                    is_dir=current_is_dir,
                    size=current_size,
                )
            )

        return entries

    def read_file(self, entry: ArchiveEntry) -> bytes:
        result = subprocess.run(
            [self._exe, "e", "-so", self._path, entry.filename],  # type: ignore[list-item]
            capture_output=True,
            timeout=120,
        )
        return result.stdout

    def close(self) -> None:
        if self._tmpdir:
            self._tmpdir.cleanup()
            self._tmpdir = None


def open_archive(path: str | Path) -> ArchiveHandler:
    """Open an archive file and return the appropriate handler.

    Raises:
        ValueError: If the file extension is not supported.
        FileNotFoundError: For RAR files when 7-Zip is not installed.
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
