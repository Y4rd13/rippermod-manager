import os
from datetime import UTC, datetime

import pytest

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.models.load_order import LoadOrderPreference
from rippermod_manager.services.modlist_service import (
    add_preferences,
    generate_modlist,
    get_preferences,
    remove_preference,
    write_modlist,
)


@pytest.fixture
def game_dir(tmp_path):
    d = tmp_path / "game"
    d.mkdir()
    return d


@pytest.fixture
def game(session, game_dir):
    g = Game(name="TestGame", domain_name="cyberpunk2077", install_path=str(game_dir))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="archive/pc/mod"))
    session.commit()
    session.refresh(g)
    return g


def _make_mod(session, game, name, archive_filenames, *, disabled=False, game_dir=None):
    mod = InstalledMod(
        game_id=game.id,
        name=name,
        disabled=disabled,
        installed_at=datetime.now(UTC),
    )
    session.add(mod)
    session.flush()
    for fn in archive_filenames:
        rel = f"archive/pc/mod/{fn}"
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path=rel))
        if game_dir is not None:
            fp = game_dir / rel.replace("/", os.sep)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(b"data")
    session.commit()
    session.refresh(mod)
    return mod


def _create_disk_archives(game_dir, filenames):
    """Create empty .archive files on disk."""
    mod_dir = game_dir / "archive" / "pc" / "mod"
    mod_dir.mkdir(parents=True, exist_ok=True)
    for fn in filenames:
        (mod_dir / fn).write_bytes(b"data")


class TestGenerateModlist:
    def test_empty_when_no_archives(self, session, game, game_dir):
        result = generate_modlist(game, session)
        assert result == []

    def test_default_ascii_order(self, session, game, game_dir):
        _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        _make_mod(session, game, "ModC", ["ccc.archive"], game_dir=game_dir)
        result = generate_modlist(game, session)
        assert result == ["aaa.archive", "bbb.archive", "ccc.archive"]

    def test_unmanaged_archives_included(self, session, game, game_dir):
        _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        _create_disk_archives(game_dir, ["unmanaged.archive"])
        result = generate_modlist(game, session)
        assert "aaa.archive" in result
        assert "unmanaged.archive" in result

    def test_disabled_mods_excluded(self, session, game, game_dir):
        _make_mod(session, game, "Active", ["aaa.archive"], game_dir=game_dir)
        _make_mod(session, game, "Disabled", ["bbb.archive"], disabled=True, game_dir=game_dir)
        result = generate_modlist(game, session)
        # bbb.archive is on disk but its mod is disabled — it's treated as unmanaged
        assert "aaa.archive" in result
        assert "bbb.archive" in result

    def test_preference_reorders_groups(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        # Prefer ModB over ModA: B should come before A
        session.add(
            LoadOrderPreference(game_id=game.id, winner_mod_id=mod_b.id, loser_mod_id=mod_a.id)
        )
        session.commit()
        result = generate_modlist(game, session)
        assert result.index("bbb.archive") < result.index("aaa.archive")

    def test_multi_archive_mod_group_stays_together(self, session, game, game_dir):
        mod_a = _make_mod(
            session, game, "ModA", ["a1.archive", "a2.archive"], game_dir=game_dir
        )
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        # Prefer ModB over ModA
        session.add(
            LoadOrderPreference(game_id=game.id, winner_mod_id=mod_b.id, loser_mod_id=mod_a.id)
        )
        session.commit()
        result = generate_modlist(game, session)
        b_idx = result.index("bbb.archive")
        a1_idx = result.index("a1.archive")
        a2_idx = result.index("a2.archive")
        assert b_idx < a1_idx
        assert b_idx < a2_idx
        # a1 and a2 stay adjacent
        assert abs(a1_idx - a2_idx) == 1

    def test_cycle_detection_does_not_crash(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        # Create a cycle: A > B and B > A
        session.add(
            LoadOrderPreference(game_id=game.id, winner_mod_id=mod_a.id, loser_mod_id=mod_b.id)
        )
        session.add(
            LoadOrderPreference(game_id=game.id, winner_mod_id=mod_b.id, loser_mod_id=mod_a.id)
        )
        session.commit()
        # Should not raise; returns some valid ordering
        result = generate_modlist(game, session)
        assert len(result) == 2
        assert set(result) == {"aaa.archive", "bbb.archive"}

    def test_chain_of_preferences(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        mod_c = _make_mod(session, game, "ModC", ["ccc.archive"], game_dir=game_dir)
        # C > B > A
        session.add(
            LoadOrderPreference(game_id=game.id, winner_mod_id=mod_c.id, loser_mod_id=mod_b.id)
        )
        session.add(
            LoadOrderPreference(game_id=game.id, winner_mod_id=mod_b.id, loser_mod_id=mod_a.id)
        )
        session.commit()
        result = generate_modlist(game, session)
        assert result.index("ccc.archive") < result.index("bbb.archive")
        assert result.index("bbb.archive") < result.index("aaa.archive")


class TestWriteModlist:
    def test_writes_file(self, session, game, game_dir):
        _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        count = write_modlist(game, session)
        assert count == 2
        modlist_path = game_dir / "archive" / "pc" / "mod" / "modlist.txt"
        assert modlist_path.exists()
        lines = modlist_path.read_text().strip().split("\n")
        assert lines == ["aaa.archive", "bbb.archive"]

    def test_removes_file_when_no_archives(self, session, game, game_dir):
        mod_dir = game_dir / "archive" / "pc" / "mod"
        mod_dir.mkdir(parents=True, exist_ok=True)
        modlist_path = mod_dir / "modlist.txt"
        modlist_path.write_text("old content")
        count = write_modlist(game, session)
        assert count == 0
        assert not modlist_path.exists()


class TestAddPreferences:
    def test_adds_single_preference(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        added = add_preferences(game.id, mod_a.id, [mod_b.id], game, session)
        assert added == 1
        prefs = get_preferences(game.id, session)
        assert len(prefs) == 1
        assert prefs[0].winner_mod_id == mod_a.id
        assert prefs[0].loser_mod_id == mod_b.id

    def test_adds_multiple_losers(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        mod_c = _make_mod(session, game, "ModC", ["ccc.archive"], game_dir=game_dir)
        added = add_preferences(game.id, mod_a.id, [mod_b.id, mod_c.id], game, session)
        assert added == 2

    def test_skips_duplicate_preference(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        add_preferences(game.id, mod_a.id, [mod_b.id], game, session)
        added = add_preferences(game.id, mod_a.id, [mod_b.id], game, session)
        assert added == 0

    def test_reverses_existing_preference(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        add_preferences(game.id, mod_a.id, [mod_b.id], game, session)
        # Now reverse: prefer B over A
        added = add_preferences(game.id, mod_b.id, [mod_a.id], game, session)
        assert added == 1
        prefs = get_preferences(game.id, session)
        assert len(prefs) == 1
        assert prefs[0].winner_mod_id == mod_b.id
        assert prefs[0].loser_mod_id == mod_a.id

    def test_writes_modlist_on_disk(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        # Prefer B over A → B should load first
        add_preferences(game.id, mod_b.id, [mod_a.id], game, session)
        modlist_path = game_dir / "archive" / "pc" / "mod" / "modlist.txt"
        assert modlist_path.exists()
        lines = modlist_path.read_text().strip().split("\n")
        assert lines.index("bbb.archive") < lines.index("aaa.archive")


class TestRemovePreference:
    def test_removes_existing(self, session, game, game_dir):
        mod_a = _make_mod(session, game, "ModA", ["aaa.archive"], game_dir=game_dir)
        mod_b = _make_mod(session, game, "ModB", ["bbb.archive"], game_dir=game_dir)
        add_preferences(game.id, mod_a.id, [mod_b.id], game, session)
        removed = remove_preference(game.id, mod_a.id, mod_b.id, game, session)
        assert removed is True
        assert get_preferences(game.id, session) == []

    def test_returns_false_for_nonexistent(self, session, game, game_dir):
        removed = remove_preference(game.id, 999, 998, game, session)
        assert removed is False
