import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from chat_nexus_mod_manager.models.game import Game, GameModPath


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    """Create a zip archive at *path* containing the given files."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.fixture
def game_setup(tmp_path, client, engine):
    """Create a game with staging directory; return (game_name, game_dir, staging)."""
    from sqlmodel import Session

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    staging = game_dir / "downloaded_mods"
    staging.mkdir()

    with Session(engine) as s:
        g = Game(name="ProfilesGame", domain_name="prg", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()

    return "ProfilesGame", game_dir, staging


def _install_mod(client, game_name, staging, archive_name, files):
    """Helper to create an archive and install it via the API."""
    archive = staging / archive_name
    _make_zip(archive, files)
    return client.post(
        f"/api/v1/games/{game_name}/install/",
        json={"archive_filename": archive_name},
    )


class TestListProfiles:
    def test_empty_initially(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.get(f"/api/v1/games/{game_name}/profiles/")
        assert r.status_code == 200
        assert r.json() == []

    def test_game_not_found_returns_404(self, client):
        r = client.get("/api/v1/games/Missing/profiles/")
        assert r.status_code == 404

    def test_returns_created_profiles(self, client, game_setup):
        game_name, _, _ = game_setup
        client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "P1"})
        client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "P2"})

        r = client.get(f"/api/v1/games/{game_name}/profiles/")
        assert r.status_code == 200
        names = [p["name"] for p in r.json()]
        assert "P1" in names
        assert "P2" in names


class TestCreateProfile:
    def test_returns_201(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "MyProfile"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "MyProfile"
        assert "id" in data

    def test_game_not_found_returns_404(self, client):
        r = client.post("/api/v1/games/Missing/profiles/", json={"name": "X"})
        assert r.status_code == 404

    def test_profile_includes_installed_mods(self, client, game_setup):
        game_name, _game_dir, staging = game_setup
        _install_mod(client, game_name, staging, "Mod1.zip", {"mods/m1.txt": b"m1"})

        r = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "WithMod"})
        assert r.status_code == 201
        data = r.json()
        assert data["mod_count"] == 1
        assert data["mods"][0]["name"] == "Mod1"

    def test_duplicate_name_replaces(self, client, game_setup):
        game_name, _, _ = game_setup
        r1 = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "Same"})
        r2 = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "Same"})
        assert r1.status_code == 201
        assert r2.status_code == 201

        profiles = client.get(f"/api/v1/games/{game_name}/profiles/").json()
        assert len(profiles) == 1


class TestGetProfile:
    def test_returns_profile(self, client, game_setup):
        game_name, _, _ = game_setup
        create_resp = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "FetchMe"})
        profile_id = create_resp.json()["id"]

        r = client.get(f"/api/v1/games/{game_name}/profiles/{profile_id}")
        assert r.status_code == 200
        assert r.json()["name"] == "FetchMe"

    def test_not_found_returns_404(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.get(f"/api/v1/games/{game_name}/profiles/99999")
        assert r.status_code == 404

    def test_game_not_found_returns_404(self, client):
        r = client.get("/api/v1/games/Missing/profiles/1")
        assert r.status_code == 404


class TestDeleteProfile:
    def test_delete_returns_204(self, client, game_setup):
        game_name, _, _ = game_setup
        create_resp = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "ToDelete"})
        profile_id = create_resp.json()["id"]

        r = client.delete(f"/api/v1/games/{game_name}/profiles/{profile_id}")
        assert r.status_code == 204

    def test_deleted_profile_no_longer_in_list(self, client, game_setup):
        game_name, _, _ = game_setup
        create_resp = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "Gone"})
        profile_id = create_resp.json()["id"]

        client.delete(f"/api/v1/games/{game_name}/profiles/{profile_id}")
        profiles = client.get(f"/api/v1/games/{game_name}/profiles/").json()
        assert all(p["id"] != profile_id for p in profiles)

    def test_not_found_returns_404(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.delete(f"/api/v1/games/{game_name}/profiles/99999")
        assert r.status_code == 404


class TestLoadProfile:
    def test_load_returns_200(self, client, game_setup):
        game_name, _, _ = game_setup
        create_resp = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "LoadMe"})
        profile_id = create_resp.json()["id"]

        r = client.post(f"/api/v1/games/{game_name}/profiles/{profile_id}/load")
        assert r.status_code == 200
        assert r.json()["name"] == "LoadMe"

    def test_load_not_found_returns_404(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.post(f"/api/v1/games/{game_name}/profiles/99999/load")
        assert r.status_code == 404

    def test_load_game_not_found_returns_404(self, client):
        r = client.post("/api/v1/games/Missing/profiles/1/load")
        assert r.status_code == 404


class TestExportProfile:
    def test_export_returns_200(self, client, game_setup):
        game_name, _game_dir, staging = game_setup
        _install_mod(client, game_name, staging, "ExMod.zip", {"mods/ex.txt": b"ex"})
        create_resp = client.post(
            f"/api/v1/games/{game_name}/profiles/", json={"name": "ExportThis"}
        )
        profile_id = create_resp.json()["id"]

        r = client.post(f"/api/v1/games/{game_name}/profiles/{profile_id}/export")
        assert r.status_code == 200
        data = r.json()
        assert data["profile_name"] == "ExportThis"
        assert data["game_name"] == game_name

    def test_export_contains_mods(self, client, game_setup):
        game_name, _game_dir, staging = game_setup
        _install_mod(client, game_name, staging, "ExportMod.zip", {"mods/em.txt": b"em"})
        create_resp = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "WithMods"})
        profile_id = create_resp.json()["id"]

        r = client.post(f"/api/v1/games/{game_name}/profiles/{profile_id}/export")
        data = r.json()
        assert data["mod_count"] == 1
        assert data["mods"][0]["name"] == "ExportMod"

    def test_export_not_found_returns_404(self, client, game_setup):
        game_name, _, _ = game_setup
        r = client.post(f"/api/v1/games/{game_name}/profiles/99999/export")
        assert r.status_code == 404


class TestImportProfile:
    def test_import_returns_201(self, client, game_setup):
        game_name, _, _ = game_setup
        payload = {
            "profile_name": "Imported",
            "game_name": game_name,
            "exported_at": datetime.now(UTC).isoformat(),
            "mod_count": 0,
            "mods": [],
        }
        r = client.post(f"/api/v1/games/{game_name}/profiles/import", json=payload)
        assert r.status_code == 201
        assert r.json()["name"] == "Imported"

    def test_import_matches_installed_mod(self, client, game_setup):
        game_name, _game_dir, staging = game_setup
        _install_mod(client, game_name, staging, "ImportMod.zip", {"mods/im.txt": b"im"})

        payload = {
            "profile_name": "ImportedProfile",
            "game_name": game_name,
            "exported_at": datetime.now(UTC).isoformat(),
            "mod_count": 1,
            "mods": [{"name": "ImportMod", "version": "", "source_archive": ""}],
        }
        r = client.post(f"/api/v1/games/{game_name}/profiles/import", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["mod_count"] == 1

    def test_import_game_not_found_returns_404(self, client):
        payload = {
            "profile_name": "X",
            "game_name": "NoGame",
            "exported_at": datetime.now(UTC).isoformat(),
            "mod_count": 0,
            "mods": [],
        }
        r = client.post("/api/v1/games/NoGame/profiles/import", json=payload)
        assert r.status_code == 404

    def test_import_skips_unmatched_mods(self, client, game_setup):
        game_name, _, _ = game_setup
        payload = {
            "profile_name": "NoMatches",
            "game_name": game_name,
            "exported_at": datetime.now(UTC).isoformat(),
            "mod_count": 1,
            "mods": [{"name": "DoesNotExist", "version": "", "source_archive": ""}],
        }
        r = client.post(f"/api/v1/games/{game_name}/profiles/import", json=payload)
        assert r.status_code == 201
        assert r.json()["mod_count"] == 0
