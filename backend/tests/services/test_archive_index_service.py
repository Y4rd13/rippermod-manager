"""Tests for the archive entry indexer service."""

from __future__ import annotations

import struct

from sqlmodel import select

from rippermod_manager.archive.rdar_parser import (
    HASH_ENTRY_SIZE,
    HEADER_SIZE,
    RDAR_MAGIC,
    TOC_PREAMBLE_SIZE,
)
from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.archive_index_service import (
    index_game_archives,
    remove_index_for_mod,
)


def _build_rdar(entries: list[tuple[int, bytes]]) -> bytes:
    """Build a minimal valid RDAR binary."""
    table_offset = HEADER_SIZE
    n = len(entries)
    file_size = HEADER_SIZE + TOC_PREAMBLE_SIZE + n * HASH_ENTRY_SIZE
    header = struct.pack("<4sIQIIQQ", RDAR_MAGIC, 12, table_offset, 1, 0, 0, file_size)
    toc_meta = struct.pack("<IIQIII", 0, 0, 0, n, 0, 0)
    hash_data = b""
    for h, sha1 in entries:
        hash_data += struct.pack("<QQIIIII", h, 0, 1, 0, 0, 0, 0) + sha1
    return header + toc_meta + hash_data


def _place_archive(tmp_path, rel_path: str, entries: list[tuple[int, bytes]]) -> None:
    """Write a synthetic .archive file at the given relative path under tmp_path."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(_build_rdar(entries))


class TestIndexGameArchives:
    def test_indexes_single_archive(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        _place_archive(tmp_path, "archive/pc/mod/a.archive", [(100, b"\xaa" * 20)])

        count = index_game_archives(game, session)
        assert count == 1

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert len(rows) == 1
        assert rows[0].resource_hash == 100
        assert rows[0].archive_filename == "a.archive"
        assert rows[0].game_id == game.id

    def test_indexes_multiple_archives(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        _place_archive(tmp_path, "archive/pc/mod/a.archive", [(1, b"\x01" * 20)])
        _place_archive(
            tmp_path,
            "archive/pc/mod/b.archive",
            [(2, b"\x02" * 20), (3, b"\x03" * 20)],
        )

        count = index_game_archives(game, session)
        assert count == 3

    def test_skips_already_indexed(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        _place_archive(tmp_path, "archive/pc/mod/a.archive", [(100, b"\xaa" * 20)])

        count1 = index_game_archives(game, session)
        assert count1 == 1

        count2 = index_game_archives(game, session)
        assert count2 == 0

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert len(rows) == 1

    def test_force_reindex_replaces(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        _place_archive(tmp_path, "archive/pc/mod/a.archive", [(100, b"\xaa" * 20)])

        index_game_archives(game, session)
        count = index_game_archives(game, session, force_reindex=True)
        assert count == 1

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert len(rows) == 1

    def test_links_to_installed_mod(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        _place_archive(tmp_path, "archive/pc/mod/mymod.archive", [(42, b"\x42" * 20)])

        mod = InstalledMod(game_id=game.id, name="MyMod")
        session.add(mod)
        session.flush()
        session.add(
            InstalledModFile(
                installed_mod_id=mod.id,
                relative_path="archive/pc/mod/mymod.archive",
            )
        )
        session.commit()

        index_game_archives(game, session)

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert len(rows) == 1
        assert rows[0].installed_mod_id == mod.id

    def test_unmanaged_archive_has_null_mod_id(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        _place_archive(tmp_path, "archive/pc/mod/unmanaged.archive", [(99, b"\x00" * 20)])

        index_game_archives(game, session)

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert len(rows) == 1
        assert rows[0].installed_mod_id is None

    def test_invalid_archive_skipped(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        corrupt = tmp_path / "archive" / "pc" / "mod" / "bad.archive"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_bytes(b"NOT_RDAR_DATA")

        _place_archive(tmp_path, "archive/pc/mod/good.archive", [(1, b"\x01" * 20)])

        count = index_game_archives(game, session)
        assert count == 1

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert len(rows) == 1
        assert rows[0].archive_filename == "good.archive"

    def test_progress_callback_called(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        _place_archive(tmp_path, "archive/pc/mod/a.archive", [(1, b"\x01" * 20)])

        calls: list[tuple[str, str, int]] = []

        def on_progress(stage: str, msg: str, pct: int) -> None:
            calls.append((stage, msg, pct))

        index_game_archives(game, session, on_progress=on_progress)
        assert len(calls) >= 2
        assert calls[0][0] == "archive-index"

    def test_no_archives_returns_zero(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        (tmp_path / "archive" / "pc" / "mod").mkdir(parents=True, exist_ok=True)

        count = index_game_archives(game, session)
        assert count == 0

    def test_sha1_hex_stored(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        sha1 = bytes(range(20))
        _place_archive(tmp_path, "archive/pc/mod/a.archive", [(1, sha1)])

        index_game_archives(game, session)

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert rows[0].sha1_hex == sha1.hex()


class TestRemoveIndexForMod:
    def test_removes_entries(self, tmp_path, session, make_game):
        game = make_game(install_path=str(tmp_path))
        _place_archive(
            tmp_path,
            "archive/pc/mod/a.archive",
            [(1, b"\x01" * 20), (2, b"\x02" * 20)],
        )

        mod = InstalledMod(game_id=game.id, name="TestMod")
        session.add(mod)
        session.flush()
        session.add(
            InstalledModFile(
                installed_mod_id=mod.id,
                relative_path="archive/pc/mod/a.archive",
            )
        )
        session.commit()

        index_game_archives(game, session)

        removed = remove_index_for_mod(session, mod.id)
        assert removed == 2

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert len(rows) == 0

    def test_removes_only_target_mod(self, session, make_game):
        game = make_game()

        session.add(
            ArchiveEntryIndex(
                game_id=game.id,
                installed_mod_id=1,
                archive_filename="a.archive",
                archive_relative_path="archive/pc/mod/a.archive",
                resource_hash=100,
            )
        )
        session.add(
            ArchiveEntryIndex(
                game_id=game.id,
                installed_mod_id=2,
                archive_filename="b.archive",
                archive_relative_path="archive/pc/mod/b.archive",
                resource_hash=200,
            )
        )
        session.flush()

        removed = remove_index_for_mod(session, 1)
        assert removed == 1

        rows = session.exec(select(ArchiveEntryIndex)).all()
        assert len(rows) == 1
        assert rows[0].installed_mod_id == 2
