import httpx
import respx

from rippermod_manager.nexus.client import BASE_URL


class TestValidateKey:
    @respx.mock
    def test_valid(self, client):
        respx.get(f"{BASE_URL}/v1/users/validate.json").mock(
            return_value=httpx.Response(200, json={"name": "user1", "is_premium": False})
        )
        r = client.post("/api/v1/nexus/validate", json={"api_key": "test"})
        assert r.status_code == 200
        assert r.json()["valid"] is True

    @respx.mock
    def test_invalid(self, client):
        respx.get(f"{BASE_URL}/v1/users/validate.json").mock(return_value=httpx.Response(401))
        r = client.post("/api/v1/nexus/validate", json={"api_key": "bad"})
        assert r.status_code == 200
        assert r.json()["valid"] is False


class TestConnectAndStore:
    @respx.mock
    def test_stores_key(self, client):
        respx.get(f"{BASE_URL}/v1/users/validate.json").mock(
            return_value=httpx.Response(200, json={"name": "user1", "is_premium": False})
        )
        r = client.post("/api/v1/nexus/connect", json={"api_key": "valid-key"})
        assert r.status_code == 200
        assert r.json()["valid"] is True
        settings = client.get("/api/v1/settings/").json()
        nexus = next((s for s in settings if s["key"] == "nexus_api_key"), None)
        assert nexus is not None

    @respx.mock
    def test_invalid_no_store(self, client):
        respx.get(f"{BASE_URL}/v1/users/validate.json").mock(return_value=httpx.Response(401))
        r = client.post("/api/v1/nexus/connect", json={"api_key": "bad"})
        assert r.json()["valid"] is False
        settings = client.get("/api/v1/settings/").json()
        assert not any(s["key"] == "nexus_api_key" for s in settings)


class TestSyncHistory:
    def test_game_not_found(self, client):
        r = client.post("/api/v1/nexus/sync-history/NoGame")
        assert r.status_code == 404

    def test_no_key_400(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.post("/api/v1/nexus/sync-history/G")
        assert r.status_code == 400

    @respx.mock
    def test_sync_success(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        client.put(
            "/api/v1/settings/",
            json={"settings": {"nexus_api_key": "valid-key"}},
        )
        respx.get(f"{BASE_URL}/v1/user/tracked_mods.json").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get(f"{BASE_URL}/v1/user/endorsements.json").mock(
            return_value=httpx.Response(200, json=[])
        )
        r = client.post("/api/v1/nexus/sync-history/G")
        assert r.status_code == 200
        assert "tracked_mods" in r.json()


class TestListDownloads:
    def test_list(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.get("/api/v1/nexus/downloads/G")
        assert r.status_code == 200
        assert r.json() == []
