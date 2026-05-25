class TestListGames:
    def test_empty(self, client):
        r = client.get("/api/v1/games/")
        assert r.status_code == 200
        assert r.json() == []


class TestCreateGame:
    def test_success(self, client):
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "TestGame",
                "domain_name": "testgame",
                "install_path": "/games/test",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "TestGame"
        assert data["domain_name"] == "testgame"

    def test_auto_cyberpunk_paths(self, client):
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "Cyberpunk 2077",
                "domain_name": "cyberpunk2077",
                "install_path": "/games/cp2077",
            },
        )
        assert r.status_code == 201
        paths = r.json()["mod_paths"]
        assert len(paths) == 10
        rels = {p["relative_path"] for p in paths}
        assert {"archive/pc/patch", "r6/config"} <= rels

    def test_custom_paths(self, client):
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "Custom",
                "domain_name": "custom",
                "install_path": "/games/custom",
                "mod_paths": [{"relative_path": "mods", "description": "Main"}],
            },
        )
        assert r.status_code == 201
        assert len(r.json()["mod_paths"]) == 1

    def test_duplicate_upserts(self, client):
        payload = {
            "name": "DupGame",
            "domain_name": "dup",
            "install_path": "/games/dup",
        }
        client.post("/api/v1/games/", json=payload)
        r = client.post(
            "/api/v1/games/",
            json={**payload, "install_path": "/games/dup2"},
        )
        assert r.status_code == 200
        assert r.json()["install_path"] == "/games/dup2"


class TestGetGame:
    def test_found(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G1", "domain_name": "g1", "install_path": "/g1"},
        )
        r = client.get("/api/v1/games/G1")
        assert r.status_code == 200
        assert r.json()["name"] == "G1"

    def test_not_found(self, client):
        r = client.get("/api/v1/games/Nonexistent")
        assert r.status_code == 404

    def test_resolved_mods_dir_default(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "DefDir", "domain_name": "dd", "install_path": "/games/dd"},
        )
        r = client.get("/api/v1/games/DefDir")
        assert r.status_code == 200
        data = r.json()
        assert data["mods_dir"] is None
        assert data["resolved_mods_dir"].replace("\\", "/") == "/games/dd/downloaded_mods"

    def test_resolved_mods_dir_with_override(self, client, tmp_path):
        custom = tmp_path / "staging"
        custom.mkdir()
        client.post(
            "/api/v1/games/",
            json={
                "name": "OvrDir",
                "domain_name": "od",
                "install_path": str(tmp_path),
                "mods_dir": str(custom),
            },
        )
        r = client.get("/api/v1/games/OvrDir")
        assert r.status_code == 200
        data = r.json()
        assert data["mods_dir"] == str(custom)
        assert data["resolved_mods_dir"] == str(custom)

    def test_post_rejects_cross_volume_mods_dir(self, client, monkeypatch, tmp_path):
        # Force same_volume to return False so this works regardless of test env layout.
        from rippermod_manager.routers import games as games_router

        monkeypatch.setattr(games_router, "same_volume", lambda a, b: False)
        install = tmp_path / "game"
        install.mkdir()
        bad_mods_dir = tmp_path / "bad"
        bad_mods_dir.mkdir()
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "CrossVol",
                "domain_name": "cv",
                "install_path": str(install),
                "mods_dir": str(bad_mods_dir),
            },
        )
        assert r.status_code == 422, r.text
        assert "same physical volume" in r.json()["detail"]

    def test_post_accepts_same_volume_mods_dir(self, client, tmp_path):
        install = tmp_path / "game"
        install.mkdir()
        custom = tmp_path / "staging"
        custom.mkdir()
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "SameVol",
                "domain_name": "sv",
                "install_path": str(install),
                "mods_dir": str(custom),
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["mods_dir"] == str(custom)
        assert r.json()["resolved_mods_dir"] == str(custom)


class TestUpdateGame:
    def test_set_mods_dir_same_volume(self, client, tmp_path):
        install = tmp_path / "game"
        install.mkdir()
        custom = tmp_path / "staging"
        custom.mkdir()
        client.post(
            "/api/v1/games/",
            json={"name": "U1", "domain_name": "u", "install_path": str(install)},
        )
        r = client.patch("/api/v1/games/U1", json={"mods_dir": str(custom)})
        assert r.status_code == 200, r.text
        assert r.json()["mods_dir"] == str(custom)
        assert r.json()["resolved_mods_dir"] == str(custom)

    def test_clear_mods_dir(self, client, tmp_path):
        install = tmp_path / "game"
        install.mkdir()
        custom = tmp_path / "staging"
        custom.mkdir()
        client.post(
            "/api/v1/games/",
            json={
                "name": "U2",
                "domain_name": "u",
                "install_path": str(install),
                "mods_dir": str(custom),
            },
        )
        r = client.patch("/api/v1/games/U2", json={"mods_dir": ""})
        assert r.status_code == 200
        assert r.json()["mods_dir"] is None
        # falls back to default
        assert r.json()["resolved_mods_dir"].endswith("downloaded_mods")

    def test_not_found(self, client):
        r = client.patch("/api/v1/games/Nonexistent", json={"mods_dir": "/x"})
        assert r.status_code == 404


class TestValidatePath:
    def test_nonexistent_path(self, client):
        r = client.post(
            "/api/v1/games/validate-path",
            json={"install_path": "/nonexistent/path"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert data["found_exe"] is False
        assert data["found_mod_dirs"] == []
        assert "not found" in data["warning"].lower()

    def test_valid_path_with_exe(self, client, tmp_path):
        # Create a fake Cyberpunk install
        exe_dir = tmp_path / "bin" / "x64"
        exe_dir.mkdir(parents=True)
        (exe_dir / "Cyberpunk2077.exe").touch()

        # Create some mod dirs
        (tmp_path / "mods").mkdir()
        (tmp_path / "archive" / "pc" / "mod").mkdir(parents=True)

        r = client.post(
            "/api/v1/games/validate-path",
            json={"install_path": str(tmp_path)},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["found_exe"] is True
        assert "mods" in data["found_mod_dirs"]
        assert "archive/pc/mod" in data["found_mod_dirs"]

    def test_unknown_domain(self, client):
        r = client.post(
            "/api/v1/games/validate-path",
            json={"install_path": "/some/path", "domain_name": "unknowngame"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert "Unknown game domain" in data["warning"]

    def test_path_without_exe(self, client, tmp_path):
        # Just create a mod dir but no exe
        (tmp_path / "mods").mkdir()

        r = client.post(
            "/api/v1/games/validate-path",
            json={"install_path": str(tmp_path)},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert data["found_exe"] is False


class TestDeleteGame:
    def test_success(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "ToDelete", "domain_name": "del", "install_path": "/d"},
        )
        r = client.delete("/api/v1/games/ToDelete")
        assert r.status_code == 204

    def test_not_found(self, client):
        r = client.delete("/api/v1/games/NoGame")
        assert r.status_code == 404
