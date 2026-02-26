import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.schemas.conflicts import ConflictSeverity
from rippermod_manager.services.conflict_service import (
    check_conflicts,
    check_installed_conflicts,
    check_pairwise_conflict,
)
from rippermod_manager.services.install_service import install_mod


def _make_zip(path, files: dict[str, bytes]) -> None:
    """Create a zip archive with the given filename -> content mapping."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


class TestCheckConflicts:
    def _setup_game(self, session, tmp_path):
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        g = Game(name="ConflictGame", domain_name="cg", install_path=str(game_dir))
        session.add(g)
        session.flush()
        session.add(GameModPath(game_id=g.id, relative_path="mods"))
        session.commit()
        session.refresh(g)
        return g, game_dir

    def test_no_conflicts_when_no_mods_installed(self, session, tmp_path):
        game, game_dir = self._setup_game(session, tmp_path)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()
        archive = staging / "NewMod.zip"
        _make_zip(archive, {"mods/newfile.txt": b"new"})

        result = check_conflicts(game, archive, session)

        assert result.total_files == 1
        assert result.conflicts == []

    def test_detects_conflict_with_installed_mod(self, session, tmp_path):
        game, game_dir = self._setup_game(session, tmp_path)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()

        # Install mod A with files a.txt and b.txt
        archive_a = staging / "ModA.zip"
        _make_zip(archive_a, {"a.txt": b"from A", "b.txt": b"from A"})
        install_mod(game, archive_a, session)

        # Check conflicts for a new archive that also contains b.txt and c.txt
        archive_b = staging / "ModB.zip"
        _make_zip(archive_b, {"b.txt": b"from B", "c.txt": b"from B"})

        result = check_conflicts(game, archive_b, session)

        assert result.total_files == 2
        assert len(result.conflicts) == 1
        assert result.conflicts[0].file_path == "b.txt"
        assert result.conflicts[0].owning_mod_name == "ModA"

    def test_conflict_result_contains_archive_filename(self, session, tmp_path):
        game, game_dir = self._setup_game(session, tmp_path)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()
        archive = staging / "CheckMe.zip"
        _make_zip(archive, {"x.txt": b"x"})

        result = check_conflicts(game, archive, session)

        assert result.archive_filename == "CheckMe.zip"

    def test_multiple_conflicts(self, session, tmp_path):
        game, game_dir = self._setup_game(session, tmp_path)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()

        archive_a = staging / "ModA.zip"
        _make_zip(archive_a, {"f1.txt": b"a", "f2.txt": b"a", "f3.txt": b"a"})
        install_mod(game, archive_a, session)

        archive_b = staging / "ModB.zip"
        _make_zip(archive_b, {"f1.txt": b"b", "f2.txt": b"b", "f4.txt": b"b"})

        result = check_conflicts(game, archive_b, session)

        assert result.total_files == 3
        assert len(result.conflicts) == 2

    def test_skips_directory_entries(self, session, tmp_path):
        game, game_dir = self._setup_game(session, tmp_path)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()
        archive = staging / "DirArchive.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.mkdir("mydir")
            zf.writestr("mydir/file.txt", b"content")

        result = check_conflicts(game, archive, session)

        # Only the file entry should be counted, not the directory
        assert result.total_files == 1

    def test_conflict_owning_mod_id_is_correct(self, session, tmp_path):
        game, game_dir = self._setup_game(session, tmp_path)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()

        archive_a = staging / "Owner.zip"
        _make_zip(archive_a, {"shared.txt": b"owner"})
        install_result = install_mod(game, archive_a, session)

        archive_b = staging / "Challenger.zip"
        _make_zip(archive_b, {"shared.txt": b"challenger"})

        result = check_conflicts(game, archive_b, session)

        assert len(result.conflicts) == 1
        assert result.conflicts[0].owning_mod_id == install_result.installed_mod_id

    def test_case_insensitive_path_matching(self, session, tmp_path):
        game, game_dir = self._setup_game(session, tmp_path)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()

        # Mod A installs "mods/File.TXT" (stored lowercase in ownership map)
        mod = InstalledMod(game_id=game.id, name="CaseMod", source_archive="case.zip")
        session.add(mod)
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="mods/File.TXT"))
        session.commit()

        # Archive contains "mods/file.txt" (lowercase) — should still conflict
        archive = staging / "NewCase.zip"
        _make_zip(archive, {"mods/file.txt": b"conflict"})

        result = check_conflicts(game, archive, session)

        assert len(result.conflicts) == 1


class TestCheckInstalledConflicts:
    def _setup_game(self, session, tmp_path):
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        staging = game_dir / "downloaded_mods"
        staging.mkdir()
        g = Game(name="ICGame", domain_name="cg", install_path=str(game_dir))
        session.add(g)
        session.flush()
        session.add(GameModPath(game_id=g.id, relative_path="mods"))
        session.commit()
        session.refresh(g)
        return g, game_dir, staging

    def _add_mod(self, session, game, staging, name, archive, files, installed_at=None):
        archive_path = staging / archive
        _make_zip(archive_path, files)
        mod = InstalledMod(
            game_id=game.id,
            name=name,
            source_archive=archive,
            installed_at=installed_at or datetime.now(UTC),
        )
        session.add(mod)
        session.flush()
        for rel_path in files:
            session.add(InstalledModFile(installed_mod_id=mod.id, relative_path=rel_path.lower()))
        session.commit()
        session.refresh(mod)
        return mod

    def test_empty_no_mods(self, session, tmp_path):
        game, _, _ = self._setup_game(session, tmp_path)
        result = check_installed_conflicts(game, session)
        assert result.conflict_pairs == []
        assert result.total_mods_checked == 0

    def test_disjoint_mods(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        self._add_mod(session, game, staging, "A", "A.zip", {"mods/a.txt": b"a"})
        self._add_mod(session, game, staging, "B", "B.zip", {"mods/b.txt": b"b"})
        result = check_installed_conflicts(game, session)
        assert result.conflict_pairs == []
        assert result.total_mods_checked == 2

    def test_overlapping_mods(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = t1 + timedelta(hours=1)
        self._add_mod(
            session,
            game,
            staging,
            "A",
            "A.zip",
            {"mods/shared.txt": b"a", "mods/a.txt": b"a"},
            installed_at=t1,
        )
        self._add_mod(
            session,
            game,
            staging,
            "B",
            "B.zip",
            {"mods/shared.txt": b"b"},
            installed_at=t2,
        )
        result = check_installed_conflicts(game, session)
        assert len(result.conflict_pairs) == 1
        assert "mods/shared.txt" in result.conflict_pairs[0].conflicting_files

    def test_severity_classification(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        # 1 file overlap -> LOW
        self._add_mod(session, game, staging, "A", "A.zip", {"mods/f1.txt": b"a"})
        self._add_mod(session, game, staging, "B", "B.zip", {"mods/f1.txt": b"b"})
        result = check_installed_conflicts(game, session)
        assert result.conflict_pairs[0].severity == ConflictSeverity.LOW

    def test_severity_filter(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        self._add_mod(session, game, staging, "A", "A.zip", {"mods/f.txt": b"a"})
        self._add_mod(session, game, staging, "B", "B.zip", {"mods/f.txt": b"b"})

        # LOW pair should NOT appear when filtering for HIGH
        result = check_installed_conflicts(game, session, severity_filter=ConflictSeverity.HIGH)
        assert result.conflict_pairs == []

        # LOW pair SHOULD appear when filtering for LOW
        result = check_installed_conflicts(game, session, severity_filter=ConflictSeverity.LOW)
        assert len(result.conflict_pairs) == 1

    def test_winner_is_later_install(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        self._add_mod(
            session,
            game,
            staging,
            "Early",
            "Early.zip",
            {"mods/f.txt": b"e"},
            installed_at=t1,
        )
        self._add_mod(
            session,
            game,
            staging,
            "Late",
            "Late.zip",
            {"mods/f.txt": b"l"},
            installed_at=t2,
        )
        result = check_installed_conflicts(game, session)
        assert result.conflict_pairs[0].winner == "Late"

    def test_three_way_conflicts(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        self._add_mod(session, game, staging, "A", "A.zip", {"mods/x.txt": b"a"})
        self._add_mod(session, game, staging, "B", "B.zip", {"mods/x.txt": b"b"})
        self._add_mod(session, game, staging, "C", "C.zip", {"mods/x.txt": b"c"})
        result = check_installed_conflicts(game, session)
        # 3 mods sharing 1 file -> C(3,2) = 3 pairs
        assert len(result.conflict_pairs) == 3

    def test_skipped_mod_missing_archive(self, session, tmp_path):
        game, _, _staging = self._setup_game(session, tmp_path)
        # Mod without archive on disk
        mod = InstalledMod(
            game_id=game.id,
            name="Ghost",
            source_archive="ghost.zip",
        )
        session.add(mod)
        session.commit()
        result = check_installed_conflicts(game, session)
        assert len(result.skipped_mods) == 1
        assert result.skipped_mods[0].mod_name == "Ghost"


class TestCheckPairwiseConflict:
    def _setup_game(self, session, tmp_path):
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        staging = game_dir / "downloaded_mods"
        staging.mkdir()
        g = Game(name="PairGame", domain_name="cg", install_path=str(game_dir))
        session.add(g)
        session.flush()
        session.add(GameModPath(game_id=g.id, relative_path="mods"))
        session.commit()
        session.refresh(g)
        return g, game_dir, staging

    def _add_mod(self, session, game, staging, name, archive, files, installed_at=None):
        archive_path = staging / archive
        _make_zip(archive_path, files)
        mod = InstalledMod(
            game_id=game.id,
            name=name,
            source_archive=archive,
            installed_at=installed_at or datetime.now(UTC),
        )
        session.add(mod)
        session.flush()
        for rel_path in files:
            session.add(InstalledModFile(installed_mod_id=mod.id, relative_path=rel_path.lower()))
        session.commit()
        session.refresh(mod)
        return mod

    def test_no_overlap(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        mod_a = self._add_mod(session, game, staging, "A", "A.zip", {"mods/a.txt": b"a"})
        mod_b = self._add_mod(session, game, staging, "B", "B.zip", {"mods/b.txt": b"b"})
        result = check_pairwise_conflict(game, mod_a, mod_b)
        assert result.conflicting_files == []
        assert result.severity is None

    def test_overlap(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        t1 = datetime(2024, 3, 1, tzinfo=UTC)
        t2 = t1 + timedelta(hours=1)
        mod_a = self._add_mod(
            session,
            game,
            staging,
            "A",
            "A.zip",
            {"mods/shared.txt": b"a"},
            installed_at=t1,
        )
        mod_b = self._add_mod(
            session,
            game,
            staging,
            "B",
            "B.zip",
            {"mods/shared.txt": b"b"},
            installed_at=t2,
        )
        result = check_pairwise_conflict(game, mod_a, mod_b)
        assert "mods/shared.txt" in result.conflicting_files
        assert result.winner == "B"

    def test_missing_archive_raises(self, session, tmp_path):
        game, _, staging = self._setup_game(session, tmp_path)
        mod_a = self._add_mod(session, game, staging, "A", "A.zip", {"mods/a.txt": b"a"})
        # mod_b has archive name but no file on disk
        mod_b = InstalledMod(
            game_id=game.id,
            name="B",
            source_archive="missing.zip",
        )
        session.add(mod_b)
        session.commit()
        session.refresh(mod_b)
        with pytest.raises(ValueError, match="unreadable"):
            check_pairwise_conflict(game, mod_a, mod_b)
