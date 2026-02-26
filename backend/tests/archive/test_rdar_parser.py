"""Tests for the RDAR .archive binary parser."""

from __future__ import annotations

import struct

import pytest

from rippermod_manager.archive.rdar_parser import (
    HASH_ENTRY_SIZE,
    HEADER_SIZE,
    RDAR_MAGIC,
    TOC_PREAMBLE_SIZE,
    parse_rdar_header,
    parse_rdar_toc,
)


def build_rdar_binary(entries: list[tuple[int, bytes]]) -> bytes:
    """Build a minimal valid RDAR .archive binary for testing.

    Args:
        entries: list of (hash_uint64, sha1_20bytes) tuples.
    """
    table_offset = HEADER_SIZE
    num_entries = len(entries)
    file_size = HEADER_SIZE + TOC_PREAMBLE_SIZE + num_entries * HASH_ENTRY_SIZE

    header = struct.pack("<4sIQQQQ", RDAR_MAGIC, 12, table_offset, 1, 0, file_size)

    toc_meta = struct.pack("<IIIIIQ", 0, 0, num_entries, num_entries, 0, 0)

    hash_data = b""
    for h, sha1 in entries:
        entry = struct.pack("<QQIIIII", h, 0, 1, 0, 0, 0, 0) + sha1
        hash_data += entry

    return header + toc_meta + hash_data


class TestParseRdarHeader:
    def test_valid_header(self):
        data = struct.pack("<4sIQQQQ", RDAR_MAGIC, 12, 0x100, 42, 0, 999)
        hdr = parse_rdar_header(data)
        assert hdr.magic == RDAR_MAGIC
        assert hdr.version == 12
        assert hdr.table_offset == 0x100
        assert hdr.archive_id == 42
        assert hdr.file_size == 999

    def test_invalid_magic_raises(self):
        data = struct.pack("<4sIQQQQ", b"NOPE", 12, 0, 0, 0, 0)
        with pytest.raises(ValueError, match="Invalid RDAR magic"):
            parse_rdar_header(data)

    def test_truncated_header_raises(self):
        with pytest.raises(ValueError, match="Header too short"):
            parse_rdar_header(b"RDAR" + b"\x00" * 10)


class TestParseRdarToc:
    def test_single_entry(self, tmp_path):
        sha1 = b"\xab" * 20
        data = build_rdar_binary([(0xDEADBEEF, sha1)])
        archive = tmp_path / "test.archive"
        archive.write_bytes(data)

        toc = parse_rdar_toc(archive)
        assert len(toc.hash_entries) == 1
        assert toc.hash_entries[0].hash == 0xDEADBEEF
        assert toc.hash_entries[0].sha1 == sha1
        assert toc.entry_count == 1

    def test_multiple_entries(self, tmp_path):
        entries = [(i * 1000, bytes([i]) * 20) for i in range(5)]
        data = build_rdar_binary(entries)
        archive = tmp_path / "multi.archive"
        archive.write_bytes(data)

        toc = parse_rdar_toc(archive)
        assert len(toc.hash_entries) == 5
        for i, entry in enumerate(toc.hash_entries):
            assert entry.hash == i * 1000
            assert entry.sha1 == bytes([i]) * 20

    def test_zero_entries(self, tmp_path):
        data = build_rdar_binary([])
        archive = tmp_path / "empty.archive"
        archive.write_bytes(data)

        toc = parse_rdar_toc(archive)
        assert len(toc.hash_entries) == 0
        assert toc.entry_count == 0

    def test_header_fields_preserved(self, tmp_path):
        data = build_rdar_binary([(1, b"\x00" * 20)])
        archive = tmp_path / "meta.archive"
        archive.write_bytes(data)

        toc = parse_rdar_toc(archive)
        assert toc.header.magic == RDAR_MAGIC
        assert toc.header.version == 12
        assert toc.header.archive_id == 1

    def test_corrupt_toc_raises(self, tmp_path):
        header = struct.pack("<4sIQQQQ", RDAR_MAGIC, 12, HEADER_SIZE, 0, 0, 100)
        archive = tmp_path / "corrupt.archive"
        archive.write_bytes(header + b"\x00" * 5)

        with pytest.raises(ValueError, match="TOC preamble truncated"):
            parse_rdar_toc(archive)

    def test_truncated_hash_entries_raises(self, tmp_path):
        table_offset = HEADER_SIZE
        header = struct.pack("<4sIQQQQ", RDAR_MAGIC, 12, table_offset, 0, 0, 200)
        toc_meta = struct.pack("<IIIIIQ", 0, 0, 3, 0, 0, 0)
        archive = tmp_path / "truncated.archive"
        archive.write_bytes(header + toc_meta + b"\x00" * 10)

        with pytest.raises(ValueError, match="Hash entries truncated"):
            parse_rdar_toc(archive)

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_rdar_toc("/nonexistent/path/test.archive")

    def test_num_chunks_parsed(self, tmp_path):
        sha1 = b"\x00" * 20
        table_offset = HEADER_SIZE
        file_size = HEADER_SIZE + TOC_PREAMBLE_SIZE + HASH_ENTRY_SIZE
        header = struct.pack("<4sIQQQQ", RDAR_MAGIC, 12, table_offset, 0, 0, file_size)
        toc_meta = struct.pack("<IIIIIQ", 0, 0, 1, 0, 0, 0)
        entry = struct.pack("<QQIIIII", 42, 999, 7, 0, 0, 0, 0) + sha1
        archive = tmp_path / "chunks.archive"
        archive.write_bytes(header + toc_meta + entry)

        toc = parse_rdar_toc(archive)
        assert toc.hash_entries[0].num_chunks == 7
        assert toc.hash_entries[0].timestamp == 999

    def test_deterministic_across_calls(self, tmp_path):
        entries = [(0xCAFE, b"\x01" * 20), (0xBEEF, b"\x02" * 20)]
        data = build_rdar_binary(entries)
        archive = tmp_path / "deterministic.archive"
        archive.write_bytes(data)

        toc1 = parse_rdar_toc(archive)
        toc2 = parse_rdar_toc(archive)
        assert toc1.hash_entries == toc2.hash_entries
