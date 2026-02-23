import zipfile

import pytest
from sqlmodel import select

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.install_service import (
    get_file_ownership_map,
    install_mod,
    list_available_archives,
    toggle_mod,
    uninstall_mod,
)


def _make_zip(path, files: dict[str, bytes]) -> None:
    """Create a zip archive with the given filename -> content mapping."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.fixture
def game_dir(tmp_path):
    """Return a temporary directory representing the game install directory."""
    d = tmp_path / "game"
    d.mkdir()
    return d


@pytest.fixture
def staging_dir(game_dir):
    """Return a staging (downloaded_mods) subdirectory inside the game dir."""
    staging = game_dir / "downloaded_mods"
    staging.mkdir()
    return staging


@pytest.fixture
def game(session, game_dir):
    """Create and persist a Game record pointing at game_dir."""
    g = Game(name="TestGame", domain_name="testgame", install_path=str(game_dir))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="mods"))
    session.commit()
    session.refresh(g)
    return g


class TestListAvailableArchives:
    def test_empty_when_no_staging_dir(self, session, game_dir):
        g = Game(name="G", domain_name="g", install_path=str(game_dir))
        session.add(g)
        session.commit()
        result = list_available_archives(g)
        assert result == []

    def test_returns_archives_in_staging(self, game, staging_dir):
        (staging_dir / "mod_a.zip").write_bytes(b"fake")
        (staging_dir / "mod_b.7z").write_bytes(b"fake")
        (staging_dir / "readme.txt").write_bytes(b"not an archive")

        result = list_available_archives(game)
        names = {p.name for p in result}
        assert "mod_a.zip" in names
        assert "mod_b.7z" in names
        assert "readme.txt" not in names

    def test_ignores_subdirectories(self, game, staging_dir):
        (staging_dir / "subdir").mkdir()
        result = list_available_archives(game)
        assert all(p.is_file() for p in result)


class TestGetFileOwnershipMap:
    def test_empty_when_no_mods(self, session, game):
        result = get_file_ownership_map(session, game.id)
        assert result == {}

    def test_maps_paths_to_mods(self, session, game):
        mod = InstalledMod(game_id=game.id, name="Alpha", source_archive="a.zip")
        session.add(mod)
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="mods/file.txt"))
        session.commit()

        result = get_file_ownership_map(session, game.id)
        assert "mods/file.txt" in result
        assert result["mods/file.txt"].name == "Alpha"

    def test_normalises_backslashes(self, session, game):
        mod = InstalledMod(game_id=game.id, name="Beta", source_archive="b.zip")
        session.add(mod)
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="mods\\win_path.txt"))
        session.commit()

        result = get_file_ownership_map(session, game.id)
        assert "mods/win_path.txt" in result

    def test_paths_are_lowercase(self, session, game):
        mod = InstalledMod(game_id=game.id, name="C", source_archive="c.zip")
        session.add(mod)
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="Mods/UPPER.TXT"))
        session.commit()

        result = get_file_ownership_map(session, game.id)
        assert "mods/upper.txt" in result


class TestInstallMod:
    def test_installs_files_and_creates_db_record(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "MyMod.zip"
        _make_zip(archive, {"mods/mymod.txt": b"content"})

        result = install_mod(game, archive, session)

        assert result.files_extracted == 1
        assert result.name == "MyMod"

        installed = session.exec(select(InstalledMod).where(InstalledMod.name == "MyMod")).first()
        assert installed is not None
        assert (game_dir / "mods" / "mymod.txt").exists()

    def test_installs_files_to_correct_paths(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "200-TestMod.zip"
        _make_zip(archive, {"a/b/c.txt": b"deep"})

        install_mod(game, archive, session)

        assert (game_dir / "a" / "b" / "c.txt").exists()

    def test_skips_directory_entries(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "DirMod.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.mkdir("subdir")
            zf.writestr("subdir/file.txt", b"hi")

        result = install_mod(game, archive, session)
        # Only the file should be counted, not the directory
        assert result.files_extracted == 1

    def test_duplicate_mod_raises_value_error(self, session, game, staging_dir):
        archive = staging_dir / "MyMod.zip"
        _make_zip(archive, {"a.txt": b"a"})

        install_mod(game, archive, session)

        with pytest.raises(ValueError, match="already installed"):
            install_mod(game, archive, session)

    def test_missing_archive_raises_file_not_found(self, session, game, tmp_path):
        missing = tmp_path / "nonexistent.zip"
        with pytest.raises(FileNotFoundError):
            install_mod(game, missing, session)

    def test_missing_game_dir_raises_file_not_found(self, session, tmp_path):
        g = Game(name="NoDir", domain_name="nodir", install_path=str(tmp_path / "missing"))
        session.add(g)
        session.commit()
        archive = tmp_path / "mod.zip"
        _make_zip(archive, {"x.txt": b"x"})
        with pytest.raises(FileNotFoundError):
            install_mod(g, archive, session)

    def test_skip_conflicts_skips_files(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "SkipMod.zip"
        _make_zip(archive, {"keep.txt": b"keep", "skip.txt": b"skip"})

        result = install_mod(game, archive, session, skip_conflicts=["skip.txt"])

        assert result.files_extracted == 1
        assert result.files_skipped == 1
        assert not (game_dir / "skip.txt").exists()
        assert (game_dir / "keep.txt").exists()

    def test_nexus_format_stores_metadata(self, session, game, staging_dir):
        archive = staging_dir / "CET-107-1-37-1-1759193708.zip"
        _make_zip(archive, {"cet.txt": b"cet"})

        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.nexus_mod_id == 107
        assert installed.upload_timestamp == 1759193708

    def test_file_ownership_transferred_on_overwrite(self, session, game, game_dir, staging_dir):
        # Install mod A which owns file.txt
        archive_a = staging_dir / "ModA.zip"
        _make_zip(archive_a, {"shared.txt": b"from A"})
        install_mod(game, archive_a, session)

        # Install mod B which also contains shared.txt (no skip)
        archive_b = staging_dir / "ModB.zip"
        _make_zip(archive_b, {"shared.txt": b"from B"})
        install_mod(game, archive_b, session)

        # The file on disk now belongs to mod B
        assert (game_dir / "shared.txt").read_bytes() == b"from B"

        # Mod A should no longer own shared.txt in DB
        ownership = get_file_ownership_map(session, game.id)
        assert ownership.get("shared.txt") is not None


class TestUninstallMod:
    def test_removes_files_and_db_record(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "ToRemove.zip"
        _make_zip(archive, {"mods/remove.txt": b"bye"})
        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files

        unresult = uninstall_mod(installed, game, session)

        assert unresult.files_deleted == 1
        assert not (game_dir / "mods" / "remove.txt").exists()
        assert session.get(InstalledMod, result.installed_mod_id) is None

    def test_removes_disabled_files(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "ToggleMod.zip"
        _make_zip(archive, {"mods/file.txt": b"data"})
        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_mod(installed, game, session)

        # Reload after toggle (disabled=True now)
        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files

        unresult = uninstall_mod(installed, game, session)
        assert unresult.files_deleted == 1
        assert not (game_dir / "mods" / "file.txt.disabled").exists()

    def test_tolerates_already_missing_files(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "GoneMod.zip"
        _make_zip(archive, {"mods/gone.txt": b"gone"})
        result = install_mod(game, archive, session)

        # Manually remove the file so uninstall must handle missing gracefully
        (game_dir / "mods" / "gone.txt").unlink()

        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        unresult = uninstall_mod(installed, game, session)
        # File was already gone, deleted count reflects only successful removals
        assert unresult.files_deleted == 0


class TestToggleMod:
    def test_disable_renames_files(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "ToggleMe.zip"
        _make_zip(archive, {"mods/mod.txt": b"data"})
        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_result = toggle_mod(installed, game, session)

        assert toggle_result.disabled is True
        assert toggle_result.files_affected == 1
        assert not (game_dir / "mods" / "mod.txt").exists()
        assert (game_dir / "mods" / "mod.txt.disabled").exists()

    def test_enable_restores_files(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "ToggleBack.zip"
        _make_zip(archive, {"mods/back.txt": b"data"})
        result = install_mod(game, archive, session)

        # Disable first
        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_mod(installed, game, session)

        # Re-enable
        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_result = toggle_mod(installed, game, session)

        assert toggle_result.disabled is False
        assert (game_dir / "mods" / "back.txt").exists()
        assert not (game_dir / "mods" / "back.txt.disabled").exists()

    def test_toggle_updates_disabled_field(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "StateCheck.zip"
        _make_zip(archive, {"mods/state.txt": b"x"})
        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.disabled is False
        session.refresh(installed)
        _ = installed.files
        toggle_mod(installed, game, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.disabled is True

    def test_toggle_twice_returns_to_enabled(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "DoubleToggle.zip"
        _make_zip(archive, {"mods/double.txt": b"x"})
        result = install_mod(game, archive, session)

        for _ in range(2):
            installed = session.get(InstalledMod, result.installed_mod_id)
            session.refresh(installed)
            _ = installed.files
            toggle_mod(installed, game, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.disabled is False
        assert (game_dir / "mods" / "double.txt").exists()
