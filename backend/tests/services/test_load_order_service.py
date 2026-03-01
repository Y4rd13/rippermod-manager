import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import select

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.load_order import (
    _compute_prefix,
    _strip_load_order_prefix,
    apply_prefer_mod,
    generate_prefer_renames,
    get_archive_load_order,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """Create an InstalledMod with archive files and optional on-disk files."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestStripLoadOrderPrefix:
    def test_no_prefix(self):
        assert _strip_load_order_prefix("mod.archive") == "mod.archive"

    def test_zz_prefix(self):
        assert _strip_load_order_prefix("zz_mod.archive") == "mod.archive"

    def test_zzz_prefix(self):
        assert _strip_load_order_prefix("zzz_mod.archive") == "mod.archive"

    def test_single_z_prefix(self):
        assert _strip_load_order_prefix("z_mod.archive") == "mod.archive"

    def test_case_insensitive(self):
        assert _strip_load_order_prefix("ZZ_mod.archive") == "mod.archive"


class TestComputePrefix:
    def test_basic_prefix(self):
        assert _compute_prefix("mod_b.archive") == "zz_"

    def test_loser_has_zz_prefix(self):
        assert _compute_prefix("zz_mod.archive") == "zzz_"

    def test_loser_has_zzz_prefix(self):
        assert _compute_prefix("zzz_mod.archive") == "zzzz_"


# ---------------------------------------------------------------------------
# TestGetArchiveLoadOrder
# ---------------------------------------------------------------------------


class TestGetArchiveLoadOrder:
    def test_empty_when_no_mods(self, session, game):
        result = get_archive_load_order(game, session)
        assert result.game_name == "TestGame"
        assert result.total_archives == 0
        assert result.load_order == []
        assert result.conflicts == []

    def test_single_mod_single_archive(self, session, game):
        _make_mod(session, game, "ModA", ["alpha.archive"])
        result = get_archive_load_order(game, session)
        assert result.total_archives == 1
        assert result.load_order[0].position == 0
        assert result.load_order[0].archive_filename == "alpha.archive"

    def test_ascii_sort_order(self, session, game):
        _make_mod(session, game, "ModM", ["mmm.archive"])
        _make_mod(session, game, "ModA", ["aaa.archive"])
        _make_mod(session, game, "ModZ", ["zzz.archive"])
        result = get_archive_load_order(game, session)
        filenames = [e.archive_filename for e in result.load_order]
        assert filenames == ["aaa.archive", "mmm.archive", "zzz.archive"]
        assert [e.position for e in result.load_order] == [0, 1, 2]

    def test_disabled_mods_excluded(self, session, game):
        _make_mod(session, game, "Active", ["active.archive"])
        _make_mod(session, game, "Disabled", ["disabled.archive"], disabled=True)
        result = get_archive_load_order(game, session)
        assert result.total_archives == 1
        assert result.load_order[0].archive_filename == "active.archive"

    def test_non_archive_files_excluded(self, session, game):
        mod = InstalledMod(game_id=game.id, name="MixedMod", installed_at=datetime.now(UTC))
        session.add(mod)
        session.flush()
        session.add(
            InstalledModFile(installed_mod_id=mod.id, relative_path="archive/pc/mod/real.archive")
        )
        session.add(
            InstalledModFile(installed_mod_id=mod.id, relative_path="archive/pc/mod/readme.txt")
        )
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="bin/x64/plugin.dll"))
        session.commit()

        result = get_archive_load_order(game, session)
        assert result.total_archives == 1
        assert result.load_order[0].archive_filename == "real.archive"

    def test_conflict_detected_winner_determined(self, session, game):
        """Two mods with the same archive filename — first in sort order wins."""
        mod_a = InstalledMod(game_id=game.id, name="ModAlpha", installed_at=datetime.now(UTC))
        mod_b = InstalledMod(game_id=game.id, name="ModBeta", installed_at=datetime.now(UTC))
        session.add_all([mod_a, mod_b])
        session.flush()
        # Same relative path claimed by both mods
        session.add(
            InstalledModFile(
                installed_mod_id=mod_a.id, relative_path="archive/pc/mod/shared.archive"
            )
        )
        session.add(
            InstalledModFile(
                installed_mod_id=mod_b.id, relative_path="archive/pc/mod/shared.archive"
            )
        )
        session.commit()

        result = get_archive_load_order(game, session)
        assert len(result.conflicts) == 1
        c = result.conflicts[0]
        # Both have the same filename "shared.archive", so both sort equally.
        # The winner/loser are determined by sort; since filenames are identical
        # the order depends on iteration, but exactly one conflict is reported.
        assert c.file_path == "archive/pc/mod/shared.archive"
        assert {c.winner_mod_id, c.loser_mod_id} == {mod_a.id, mod_b.id}


# ---------------------------------------------------------------------------
# TestGeneratePreferRenames
# ---------------------------------------------------------------------------


class TestGeneratePreferRenames:
    def test_no_rename_when_loser_already_sorts_after(self, session, game):
        winner = _make_mod(session, game, "Winner", ["aaa_win.archive"])
        loser = _make_mod(session, game, "Loser", ["zzz_lose.archive"])
        renames = generate_prefer_renames(winner, loser, game, session)
        assert renames == []

    def test_basic_zz_prefix_on_loser(self, session, game):
        winner = _make_mod(session, game, "Winner", ["bbb.archive"])
        loser = _make_mod(session, game, "Loser", ["aaa.archive"])
        renames = generate_prefer_renames(winner, loser, game, session)
        assert len(renames) == 1
        assert renames[0].new_filename == "zz_aaa.archive"
        assert renames[0].old_filename == "aaa.archive"
        assert renames[0].owning_mod_id == loser.id

    def test_escalating_prefix_when_winner_has_zz(self, session, game):
        winner = _make_mod(session, game, "Winner", ["zz_bbb.archive"])
        loser = _make_mod(session, game, "Loser", ["aaa.archive"])
        renames = generate_prefer_renames(winner, loser, game, session)
        assert len(renames) == 1
        assert renames[0].new_filename == "zzz_aaa.archive"

    def test_existing_prefix_stripped_before_new(self, session, game):
        # Loser has old prefix that needs to be replaced with a higher one
        winner = _make_mod(session, game, "Winner", ["zzz_bbb.archive"])
        loser = _make_mod(session, game, "Loser", ["zz_aaa.archive"])
        renames = generate_prefer_renames(winner, loser, game, session)
        assert len(renames) == 1
        # Old zz_ stripped, new zzzz_ applied (one more z than winner's zzz_)
        assert renames[0].new_filename == "zzzz_aaa.archive"
        assert renames[0].old_filename == "zz_aaa.archive"

    def test_multi_archive_loser_all_renamed(self, session, game):
        winner = _make_mod(session, game, "Winner", ["bbb.archive"])
        loser = _make_mod(session, game, "Loser", ["a1.archive", "a2.archive"])
        renames = generate_prefer_renames(winner, loser, game, session)
        assert len(renames) == 2
        new_names = {r.new_filename for r in renames}
        assert new_names == {"zz_a1.archive", "zz_a2.archive"}


# ---------------------------------------------------------------------------
# TestApplyPreferMod
# ---------------------------------------------------------------------------


class TestApplyPreferMod:
    def test_dry_run_returns_plan_without_touching_filesystem(self, session, game, game_dir):
        winner = _make_mod(session, game, "Winner", ["bbb.archive"], game_dir=game_dir)
        loser = _make_mod(session, game, "Loser", ["aaa.archive"], game_dir=game_dir)
        result = apply_prefer_mod(winner, loser, game, session, dry_run=True)
        assert result.success is True
        assert result.dry_run is True
        assert len(result.renames) == 1
        # Loser's original file should still exist
        assert (game_dir / "archive" / "pc" / "mod" / "aaa.archive").exists()
        # Renamed file should not exist
        assert not (game_dir / "archive" / "pc" / "mod" / "zz_aaa.archive").exists()

    def test_apply_renames_loser_files_on_disk(self, session, game, game_dir):
        winner = _make_mod(session, game, "Winner", ["bbb.archive"], game_dir=game_dir)
        loser = _make_mod(session, game, "Loser", ["aaa.archive"], game_dir=game_dir)
        result = apply_prefer_mod(winner, loser, game, session)
        assert result.success is True
        assert result.dry_run is False
        # Loser's archive is renamed (demoted)
        assert not (game_dir / "archive" / "pc" / "mod" / "aaa.archive").exists()
        assert (game_dir / "archive" / "pc" / "mod" / "zz_aaa.archive").exists()
        # Winner's archive is untouched
        assert (game_dir / "archive" / "pc" / "mod" / "bbb.archive").exists()

    def test_apply_updates_loser_db_path(self, session, game, game_dir):
        winner = _make_mod(session, game, "Winner", ["bbb.archive"], game_dir=game_dir)
        loser = _make_mod(session, game, "Loser", ["aaa.archive"], game_dir=game_dir)
        apply_prefer_mod(winner, loser, game, session)
        updated = session.exec(
            select(InstalledModFile).where(InstalledModFile.installed_mod_id == loser.id)
        ).all()
        archive_files = [f for f in updated if f.relative_path.endswith(".archive")]
        assert len(archive_files) == 1
        assert archive_files[0].relative_path == "archive/pc/mod/zz_aaa.archive"

    def test_rollback_on_partial_failure(self, session, game, game_dir):
        winner = _make_mod(session, game, "Winner", ["bbb.archive"], game_dir=game_dir)
        loser = _make_mod(session, game, "Loser", ["a1.archive", "a2.archive"], game_dir=game_dir)

        _original_rename = Path.rename
        call_count = 0

        def failing_rename(self_path, target):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError("disk error")
            return _original_rename(self_path, target)

        with patch.object(Path, "rename", failing_rename):
            result = apply_prefer_mod(winner, loser, game, session)

        assert result.success is False
        assert result.rollback_performed is True
        assert "disk error" in result.message

    def test_validation_rejects_missing_source(self, session, game, game_dir):
        # Create loser mod in DB but don't create files on disk
        winner = _make_mod(session, game, "Winner", ["bbb.archive"], game_dir=game_dir)
        loser = _make_mod(session, game, "Loser", ["aaa.archive"])
        result = apply_prefer_mod(winner, loser, game, session)
        assert result.success is False
        assert "Source file not found" in result.message

    def test_validation_rejects_target_collision(self, session, game, game_dir):
        winner = _make_mod(session, game, "Winner", ["bbb.archive"], game_dir=game_dir)
        loser = _make_mod(session, game, "Loser", ["aaa.archive"], game_dir=game_dir)
        # Pre-create the target file to cause collision
        target = game_dir / "archive" / "pc" / "mod" / "zz_aaa.archive"
        target.write_bytes(b"blocker")
        result = apply_prefer_mod(winner, loser, game, session)
        assert result.success is False
        assert "Target already exists" in result.message
