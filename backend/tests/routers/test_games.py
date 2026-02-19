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
        assert len(paths) == 7

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

    def test_duplicate_400(self, client):
        payload = {
            "name": "DupGame",
            "domain_name": "dup",
            "install_path": "/games/dup",
        }
        client.post("/api/v1/games/", json=payload)
        r = client.post("/api/v1/games/", json=payload)
        assert r.status_code == 400


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
