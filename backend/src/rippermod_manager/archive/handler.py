"""Abstract archive handler with implementations for ZIP, 7z, and RAR.

Provides a uniform interface for listing and extracting files from
mod archives regardless of format.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

SUPPORTED_EXTENSIONS = {".zip", ".7z", ".rar"}

# Default install locations of the RAR-capable tools. Their installers do not
# add themselves to PATH, so rarfile alone would not find them.
SEVENZIP_CANDIDATES: tuple[str, ...] = (
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
)
UNRAR_CANDIDATES: tuple[str, ...] = (r"C:\Program Files\WinRAR\UnRAR.exe",)

RAR_TOOL_MISSING_MESSAGE = (
    "Could not open .rar archive: RipperMod needs a RAR extractor (7-Zip or WinRAR) "
    "and found none in C:\\Program Files\\7-Zip, C:\\Program Files (x86)\\7-Zip, "
    "C:\\Program Files\\WinRAR or on your PATH. Install 7-Zip (https://www.7-zip.org/) "
    "with its default options and try again, or extract the .rar manually and drop "
    "the contents into your game's downloaded_mods/ folder."
)


def configure_rar_tools() -> None:
    """Point rarfile at 7-Zip or WinRAR in their default folders, if present.

    rarfile 4.2 caches the tool it picked, so the cache is reset whenever a
    tool path changes. A tool that does not run is not an error here: the
    read paths translate it into ``RAR_TOOL_MISSING_MESSAGE``.
    """
    import rarfile

    changed = False
    for attr, candidates in (
        ("SEVENZIP_TOOL", SEVENZIP_CANDIDATES),
        ("UNRAR_TOOL", UNRAR_CANDIDATES),
    ):
        found = next((c for c in candidates if Path(c).is_file()), None)
        if found and getattr(rarfile, attr) != found:
            setattr(rarfile, attr, found)
            changed = True
    if changed:
        with contextlib.suppress(rarfile.RarExecError):
            rarfile.tool_setup(force=True)


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    filename: str
    is_dir: bool
    size: int = 0
    compressed_size: int | None = None


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
    def open_entry(self, entry: ArchiveEntry) -> BinaryIO:
        """Open a single file entry as a readable binary stream."""

    def extract_entries(
        self, targets: list[tuple[ArchiveEntry, Path]], scratch_dir: Path
    ) -> set[str]:
        """Stream each ``(entry, dest)`` pair to *dest*, one entry open at a time.

        *scratch_dir* is where a format that cannot stream may stage files;
        it should be on the same volume as the destinations. Returns the
        filenames of the entries that were written.
        """
        written: set[str] = set()
        for entry, dest in targets:
            if entry.is_dir:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with self.open_entry(entry) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            written.add(entry.filename)
        return written

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
                    compressed_size=info.compress_size,
                )
            )
        return entries

    def read_file(self, entry: ArchiveEntry) -> bytes:
        return self._zf.read(entry.filename)

    def open_entry(self, entry: ArchiveEntry) -> BinaryIO:
        return self._zf.open(entry.filename)  # type: ignore[return-value]

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
                    compressed_size=getattr(entry, "compressed", None),
                )
            )
        return entries

    def _reject_unsafe_entries(self) -> None:
        """Raise ``ValueError`` unless every entry is a regular file or directory.

        Symlinks in a .7z can chain out of the extraction directory
        (CVE-2026-23879), and junctions, reparse points, sockets and other
        special entries are no safer. Mods ship none of them, so this is an
        allowlist over ``ArchiveFile`` (``self._archive.files``), which, unlike
        the ``FileInfo`` that ``list()`` returns, exposes junctions and sockets.
        A junction also carries the directory bit, so the special-type checks
        run before ``is_directory`` is trusted.
        """
        for f in self._archive.files:
            special = f.is_symlink or f.is_junction or f.is_socket
            if special or not (f.is_file or f.is_directory):
                raise ValueError(
                    f"Refusing to extract .7z archive: entry '{f.filename}' is a symbolic "
                    "link, junction or other special file, which mod archives never need."
                )

    def _extract_to_bytes(self, targets: list[str]) -> dict[str, bytes]:
        """Extract *targets* to a temp dir and return their contents as bytes."""
        import py7zr

        self._reject_unsafe_entries()
        self._archive.reset()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir).resolve()
            try:
                self._archive.extract(path=tmpdir, targets=targets)
            except py7zr.exceptions.Bad7zFile as exc:
                raise ValueError(f"Could not extract .7z archive: {exc}") from exc
            result: dict[str, bytes] = {}
            for name in targets:
                extracted = (tmpdir_path / name).resolve()
                if extracted.is_file() and tmpdir_path in extracted.parents:
                    result[name] = extracted.read_bytes()
        return result

    def extract_entries(
        self, targets: list[tuple[ArchiveEntry, Path]], scratch_dir: Path
    ) -> set[str]:
        """Extract straight to disk (py7zr cannot stream) and move into place.

        Files land in a temporary directory under *scratch_dir* (same volume
        as the destinations, so ``os.replace`` is a rename) and never pass
        through memory whole. Symlinks and paths that resolve outside the
        temporary directory are refused.
        """
        import py7zr

        files = [(e, d) for e, d in targets if not e.is_dir]
        if not files:
            return set()
        self._reject_unsafe_entries()
        self._archive.reset()
        written: set[str] = set()
        placed: dict[str, Path] = {}
        with tempfile.TemporaryDirectory(dir=scratch_dir) as tmpdir:
            tmp_root = Path(tmpdir).resolve()
            try:
                self._archive.extract(
                    path=tmpdir, targets=list(dict.fromkeys(e.filename for e, _ in files))
                )
            except py7zr.exceptions.Bad7zFile as exc:
                raise ValueError(f"Could not extract .7z archive: {exc}") from exc
            for entry, dest in files:
                if entry.filename in placed:
                    # Same entry, another destination: the extracted file already moved.
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(placed[entry.filename], dest)
                    continue
                extracted = Path(tmpdir) / entry.filename
                if extracted.is_symlink():
                    raise ValueError(
                        f"Refusing to extract .7z archive: '{entry.filename}' is a symbolic link."
                    )
                resolved = extracted.resolve()
                if tmp_root not in resolved.parents:
                    raise ValueError(
                        f"Refusing to extract .7z archive: '{entry.filename}' escapes the "
                        "extraction directory."
                    )
                if not resolved.is_file():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(resolved, dest)
                placed[entry.filename] = dest
                written.add(entry.filename)
        return written

    def open_entry(self, entry: ArchiveEntry) -> BinaryIO:
        """Extract *entry* to a temporary file on disk and return it opened."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "entry"
            if entry.filename not in self.extract_entries([(entry, dest)], Path(tmpdir)):
                raise KeyError(f"There is no item named '{entry.filename}' in the archive")
            out = tempfile.TemporaryFile()  # noqa: SIM115 - returned open to the caller
            with open(dest, "rb") as src:
                shutil.copyfileobj(src, out)
        out.seek(0)
        return out  # type: ignore[return-value]

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
    """Handler for .rar archives using the rarfile library.

    ``rarfile`` is a Python wrapper around an external CLI extractor.  It
    searches PATH for these tools in order: ``unrar``, ``unar``, ``7z``,
    ``7zz``, ``bsdtar``.  If any one of those is present, RAR extraction
    works transparently.  If none are present, every operation raises
    :class:`rarfile.RarCannotExec`.

    We don't bundle an extractor with the installer (UnRAR's license has
    known GPL-compatibility concerns, and bundling 7-Zip would inflate the
    installer significantly).  Most experienced modders already have 7-Zip
    or WinRAR installed system-wide; only users with a clean install hit
    this error.

    Before opening, :func:`configure_rar_tools` points rarfile at 7-Zip or
    WinRAR in their default install folders, which are not on PATH by
    default. Any ``RarExecError`` (``RarCannotExec`` included) on open, read
    or extract becomes the actionable ``RAR_TOOL_MISSING_MESSAGE`` so the
    install endpoint surfaces a useful message instead of a silent 500.
    """

    def __init__(self, path: str | Path) -> None:
        try:
            import rarfile
        except ImportError as exc:
            raise ImportError("rarfile is required for .rar support: pip install rarfile") from exc
        configure_rar_tools()
        try:
            self._rf = rarfile.RarFile(str(path), "r")
        except rarfile.RarExecError as exc:
            raise ValueError(RAR_TOOL_MISSING_MESSAGE) from exc

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for info in self._rf.infolist():
            entries.append(
                ArchiveEntry(
                    filename=info.filename,
                    is_dir=info.is_dir(),
                    size=info.file_size,
                    compressed_size=info.compress_size,
                )
            )
        return entries

    def read_file(self, entry: ArchiveEntry) -> bytes:
        import rarfile

        try:
            return self._rf.read(entry.filename)
        except rarfile.RarExecError as exc:
            raise ValueError(RAR_TOOL_MISSING_MESSAGE) from exc

    def read_all_files(self, entries: list[ArchiveEntry]) -> dict[str, bytes]:
        import rarfile

        try:
            return super().read_all_files(entries)
        except rarfile.RarExecError as exc:
            raise ValueError(RAR_TOOL_MISSING_MESSAGE) from exc

    def open_entry(self, entry: ArchiveEntry) -> BinaryIO:
        import rarfile

        try:
            return self._rf.open(entry.filename)  # type: ignore[return-value]
        except rarfile.RarExecError as exc:
            raise ValueError(RAR_TOOL_MISSING_MESSAGE) from exc

    def extract_entries(
        self, targets: list[tuple[ArchiveEntry, Path]], scratch_dir: Path
    ) -> set[str]:
        import rarfile

        # The external tool may only fail once the stream is read.
        try:
            return super().extract_entries(targets, scratch_dir)
        except rarfile.RarExecError as exc:
            raise ValueError(RAR_TOOL_MISSING_MESSAGE) from exc

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
