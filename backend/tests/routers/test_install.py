import zipfile
from pathlib import Path

import pytest

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    """Create a zip archive at *path* containing the given files."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.fixture
def game_setup(tmp_path, client, engine):
    """Create a game with a filesystem structure and return (game_name, game_dir, staging_dir)."""
    from sqlmodel import Session

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    staging = game_dir / "downloaded_mods"
    staging.mkdir()

    with Session(engine) as s:
        g = Game(name="InstallGame", domain_name="ig", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()

    return "InstallGame", game_dir, staging


class TestListAvailableArchives:
    def test_returns_empty_when_no_staging_dir(self, client, engine, tmp_path):
        from sqlmodel import Session

        game_dir = tmp_path / "nodl"
        game_dir.mkdir()

        with Session(engine) as s:
            g = Game(name="NoStaging", domain_name="ns", install_path=str(game_dir))
            s.add(g)
            s.commit()

        r = client.get("/api/v1/games/NoStaging/install/available")
        assert r.status_code == 200
        assert r.json() == []

    def test_lists_zip_archives(self, client, game_setup):
        game_name, _game_dir, staging = game_setup
        (staging / "mod_a.zip").write_bytes(b"fake")
        (staging / "not_an_archive.txt").write_bytes(b"text")

        r = client.get(f"/api/v1/games/{game_name}/install/available")
        assert r.status_code == 200
        data = r.json()
        names = [a["filename"] for a in data]
        assert "mod_a.zip" in names
        assert "not_an_archive.txt" not in names

    def test_game_not_found_returns_404(self, client):
        r = client.get("/api/v1/games/NoSuchGame/install/available")
        assert r.status_code == 404

    def test_parses_nexus_filename(self, client, game_setup):
        game_name, _, staging = game_setup
        (staging / "CET-107-1-37-1-1759193708.zip").write_bytes(b"fake")

        r = client.get(f"/api/v1/games/{game_name}/install/available")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["nexus_mod_id"] == 107


class TestListInstalledMods:
    def test_returns_empty_initially(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.get(f"/api/v1/games/{game_name}/install/installed")
        assert r.status_code == 200
        assert r.json() == []

    def test_game_not_found_returns_404(self, client):
        r = client.get("/api/v1/games/Missing/install/installed")
        assert r.status_code == 404

    def test_returns_installed_mods(self, client, game_setup, engine):
        game_name, _, _ = game_setup
        from sqlmodel import Session, select

        with Session(engine) as s:
            game = s.exec(select(Game).where(Game.name == game_name)).first()
            mod = InstalledMod(game_id=game.id, name="TestMod", source_archive="test.zip")
            s.add(mod)
            s.commit()

        r = client.get(f"/api/v1/games/{game_name}/install/installed")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "TestMod"
        assert data[0]["disabled"] is False


class TestInstallEndpoint:
    def test_install_returns_201(self, client, game_setup):
        game_name, _game_dir, staging = game_setup
        archive = staging / "NewMod.zip"
        _make_zip(archive, {"mods/new.txt": b"content"})

        r = client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "NewMod.zip"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "NewMod"
        assert data["files_extracted"] == 1

    def test_archive_not_found_returns_404(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "doesnotexist.zip"},
        )
        assert r.status_code == 404

    def test_game_not_found_returns_404(self, client):
        r = client.post(
            "/api/v1/games/Missing/install/",
            json={"archive_filename": "mod.zip"},
        )
        assert r.status_code == 404

    def test_duplicate_install_returns_409(self, client, game_setup):
        game_name, _, staging = game_setup
        archive = staging / "DupMod.zip"
        _make_zip(archive, {"mods/dup.txt": b"content"})

        client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "DupMod.zip"},
        )
        r = client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "DupMod.zip"},
        )
        assert r.status_code == 409

    def test_install_with_skip_conflicts(self, client, game_setup):
        game_name, _, staging = game_setup
        archive_a = staging / "ModA.zip"
        _make_zip(archive_a, {"shared.txt": b"from A"})
        client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "ModA.zip"},
        )

        archive_b = staging / "ModB.zip"
        _make_zip(archive_b, {"shared.txt": b"from B", "unique.txt": b"unique"})
        r = client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "ModB.zip", "skip_conflicts": ["shared.txt"]},
        )
        assert r.status_code == 201
        assert r.json()["files_skipped"] == 1


class TestUninstallEndpoint:
    def test_uninstall_returns_200(self, client, game_setup, engine):
        game_name, _game_dir, staging = game_setup
        archive = staging / "RemoveMod.zip"
        _make_zip(archive, {"mods/rm.txt": b"bye"})

        install_resp = client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "RemoveMod.zip"},
        )
        mod_id = install_resp.json()["installed_mod_id"]

        r = client.delete(f"/api/v1/games/{game_name}/install/installed/{mod_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["files_deleted"] == 1

    def test_uninstall_not_found_returns_404(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.delete(f"/api/v1/games/{game_name}/install/installed/99999")
        assert r.status_code == 404

    def test_uninstall_wrong_game_returns_404(self, client, game_setup, engine, tmp_path):
        """A mod from a different game cannot be uninstalled via another game's route."""
        game_name, _game_dir, staging = game_setup
        archive = staging / "OtherMod.zip"
        _make_zip(archive, {"mods/o.txt": b"other"})
        install_resp = client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "OtherMod.zip"},
        )
        mod_id = install_resp.json()["installed_mod_id"]

        # Create a second game
        from sqlmodel import Session

        game_dir2 = tmp_path / "game2"
        game_dir2.mkdir()
        with Session(engine) as s:
            g2 = Game(name="OtherGame", domain_name="og", install_path=str(game_dir2))
            s.add(g2)
            s.commit()

        r = client.delete(f"/api/v1/games/OtherGame/install/installed/{mod_id}")
        assert r.status_code == 404


class TestToggleEndpoint:
    def test_toggle_disables_mod(self, client, game_setup):
        game_name, _, staging = game_setup
        archive = staging / "TogMod.zip"
        _make_zip(archive, {"mods/tog.txt": b"t"})
        install_resp = client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "TogMod.zip"},
        )
        mod_id = install_resp.json()["installed_mod_id"]

        r = client.patch(f"/api/v1/games/{game_name}/install/installed/{mod_id}/toggle")
        assert r.status_code == 200
        data = r.json()
        assert data["disabled"] is True
        assert data["files_affected"] == 1

    def test_toggle_re_enables_mod(self, client, game_setup):
        game_name, _, staging = game_setup
        archive = staging / "TogBack.zip"
        _make_zip(archive, {"mods/back.txt": b"x"})
        install_resp = client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "TogBack.zip"},
        )
        mod_id = install_resp.json()["installed_mod_id"]

        client.patch(f"/api/v1/games/{game_name}/install/installed/{mod_id}/toggle")
        r = client.patch(f"/api/v1/games/{game_name}/install/installed/{mod_id}/toggle")
        assert r.status_code == 200
        assert r.json()["disabled"] is False

    def test_toggle_not_found_returns_404(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.patch(f"/api/v1/games/{game_name}/install/installed/99999/toggle")
        assert r.status_code == 404


class TestConflictsEndpoint:
    def test_no_conflicts_returns_empty_list(self, client, game_setup):
        game_name, _, staging = game_setup
        archive = staging / "Clean.zip"
        _make_zip(archive, {"mods/clean.txt": b"clean"})

        r = client.get(
            f"/api/v1/games/{game_name}/install/conflicts",
            params={"archive_filename": "Clean.zip"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["conflicts"] == []
        assert data["total_files"] == 1

    def test_detects_conflict(self, client, game_setup):
        game_name, _, staging = game_setup
        archive_a = staging / "ConflictA.zip"
        _make_zip(archive_a, {"shared.txt": b"a"})
        client.post(
            f"/api/v1/games/{game_name}/install/",
            json={"archive_filename": "ConflictA.zip"},
        )

        archive_b = staging / "ConflictB.zip"
        _make_zip(archive_b, {"shared.txt": b"b"})
        r = client.get(
            f"/api/v1/games/{game_name}/install/conflicts",
            params={"archive_filename": "ConflictB.zip"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["owning_mod_name"] == "ConflictA"

    def test_archive_not_found_returns_404(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.get(
            f"/api/v1/games/{game_name}/install/conflicts",
            params={"archive_filename": "ghost.zip"},
        )
        assert r.status_code == 404

    def test_game_not_found_returns_404(self, client):
        r = client.get(
            "/api/v1/games/NoGame/install/conflicts",
            params={"archive_filename": "any.zip"},
        )
        assert r.status_code == 404
