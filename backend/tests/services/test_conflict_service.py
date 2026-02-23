import zipfile

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.conflict_service import check_conflicts
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
