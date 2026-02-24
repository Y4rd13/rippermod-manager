import httpx
import respx

from rippermod_manager.nexus.client import BASE_URL


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
