"""Pre-extraction limits that keep a hostile archive from filling the disk.

Checked against the sizes the archive declares before anything is written,
so a decompression bomb is refused without decompressing it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rippermod_manager.archive.handler import ArchiveEntry

MAX_COMPRESSION_RATIO = 1000
RATIO_MIN_BYTES = 100 * 1024**2
FREE_SPACE_MARGIN_BYTES = 1024**3


def _exceeds_ratio(entry: ArchiveEntry) -> bool:
    size = entry.size
    compressed = entry.compressed_size
    return (
        size > RATIO_MIN_BYTES
        and compressed is not None
        and (compressed == 0 or size > MAX_COMPRESSION_RATIO * compressed)
    )


def check_extraction_budget(entries: list[ArchiveEntry], staging_dir: Path) -> None:
    """Raise ``ValueError`` if extracting *entries* into *staging_dir* is unsafe.

    Refused when one entry declares a compression ratio above
    ``MAX_COMPRESSION_RATIO``:1 while weighing more than ``RATIO_MIN_BYTES``
    uncompressed (an unknown compressed size, as in solid 7z blocks, skips the
    ratio check), or when the total uncompressed size exceeds the staging
    volume's free space minus ``FREE_SPACE_MARGIN_BYTES``.
    """
    files = [e for e in entries if not e.is_dir]
    for entry in files:
        if _exceeds_ratio(entry):
            raise ValueError(
                f"Refusing to extract '{entry.filename}': its compression ratio is above "
                f"{MAX_COMPRESSION_RATIO}:1 ({entry.size} bytes from "
                f"{entry.compressed_size}), which looks like a decompression bomb."
            )
    total = sum(e.size for e in files)
    free = shutil.disk_usage(staging_dir).free
    if total > free - FREE_SPACE_MARGIN_BYTES:
        raise ValueError(
            f"Not enough free space to extract this archive: it needs {total} bytes and "
            f"the staging drive has {free} bytes free (RipperMod keeps "
            f"{FREE_SPACE_MARGIN_BYTES // 1024**3} GiB in reserve)."
        )


def ensure_inside(root: Path, written: Path) -> None:
    """Raise ``ValueError`` if *written* does not resolve inside *root*."""
    try:
        written.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Refusing to install: extracted file '{written}' resolves outside the staging folder."
        ) from exc
