"""Abstract archive handler with implementations for ZIP, 7z, and RAR.

Provides a uniform interface for listing and extracting files from
mod archives regardless of format.
"""

from __future__ import annotations

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
        if result.returncode != 0:
            raise RuntimeError(f"7z list failed (exit {result.returncode}): {result.stderr}")

        entries: list[ArchiveEntry] = []
        current_path = ""
        current_size = 0
        current_is_dir = False

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Path = "):
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
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise RuntimeError(f"7z extract failed (exit {result.returncode}): {stderr}")
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
