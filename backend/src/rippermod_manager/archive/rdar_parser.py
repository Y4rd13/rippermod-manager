"""Parser for Cyberpunk 2077 RDAR .archive files.

Reads only the header and table-of-contents to extract 64-bit entry
hashes and SHA-1 digests without extracting or decompressing file data.

Format reference:
  https://www.zenhax.com/viewtopic.php@t=14565.html
  https://github.com/mmbednarek/rdar
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

RDAR_MAGIC = b"RDAR"
HEADER_SIZE = 0x28  # 40 bytes
TOC_PREAMBLE_SIZE = 28  # 5x uint32 + 1x uint64
HASH_ENTRY_SIZE = 0x38  # 56 bytes
MAX_HASH_TABLE_BYTES = 512 * 1024 * 1024  # 512 MB sanity limit

# struct formats (little-endian)
_HEADER_FMT = "<4sIQQQQ"
_TOC_PREAMBLE_FMT = "<IIIIIQ"
_HASH_ENTRY_FMT = "<QQIIIII"  # 36 bytes; remaining 20 bytes are SHA-1


@dataclass(frozen=True, slots=True)
class RdarHeader:
    magic: bytes
    version: int
    table_offset: int
    archive_id: int
    file_size: int


@dataclass(frozen=True, slots=True)
class RdarHashEntry:
    hash: int  # uint64 resource identifier
    timestamp: int  # uint64
    num_chunks: int  # uint32
    sha1: bytes  # 20 bytes


@dataclass(frozen=True, slots=True)
class RdarToc:
    header: RdarHeader
    hash_entries: list[RdarHashEntry]
    entry_count: int  # total file/item entries (for stats)


def parse_rdar_header(data: bytes) -> RdarHeader:
    """Parse the 40-byte RDAR header from raw bytes."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Header too short: {len(data)} bytes, need {HEADER_SIZE}")
    magic = data[0:4]
    if magic != RDAR_MAGIC:
        raise ValueError(f"Invalid RDAR magic: {magic!r}")
    _, version, table_offset, archive_id, _dummy, file_size = struct.unpack_from(
        _HEADER_FMT, data, 0
    )
    return RdarHeader(
        magic=magic,
        version=version,
        table_offset=table_offset,
        archive_id=archive_id,
        file_size=file_size,
    )


def parse_rdar_toc(file_path: str | Path) -> RdarToc:
    """Read an .archive file and parse its header + TOC.

    Only reads header (40 B) + TOC preamble (28 B) + hash entries
    (56 B each).  Does NOT read file data or decompress anything.
    """
    file_path = Path(file_path)
    with file_path.open("rb") as f:
        header_bytes = f.read(HEADER_SIZE)
        header = parse_rdar_header(header_bytes)

        if header.table_offset > header.file_size:
            raise ValueError(
                f"table_offset ({header.table_offset}) exceeds file_size ({header.file_size})"
            )

        f.seek(header.table_offset)
        toc_meta = f.read(TOC_PREAMBLE_SIZE)
        if len(toc_meta) < TOC_PREAMBLE_SIZE:
            raise ValueError("TOC preamble truncated")

        _num, _size, num_files, _num_offsets, _num_hashes, _checksum = struct.unpack_from(
            _TOC_PREAMBLE_FMT, toc_meta, 0
        )

        hash_data_size = num_files * HASH_ENTRY_SIZE
        if hash_data_size > MAX_HASH_TABLE_BYTES:
            raise ValueError(
                f"Unreasonable hash table size: {num_files} entries "
                f"({hash_data_size} bytes) — file likely corrupt"
            )
        hash_data = f.read(hash_data_size)
        if len(hash_data) < hash_data_size:
            raise ValueError(
                f"Hash entries truncated: got {len(hash_data)}, "
                f"expected {hash_data_size} ({num_files} entries)"
            )

    entries: list[RdarHashEntry] = []
    for i in range(num_files):
        offset = i * HASH_ENTRY_SIZE
        h, ts, num_chunks, _i1, _l1, _i2, _l2 = struct.unpack_from(
            _HASH_ENTRY_FMT, hash_data, offset
        )
        sha1 = hash_data[offset + 36 : offset + 56]
        entries.append(RdarHashEntry(hash=h, timestamp=ts, num_chunks=num_chunks, sha1=sha1))

    return RdarToc(header=header, hash_entries=entries, entry_count=num_files)
