"""Tests for the framework monitor endpoint."""

from rippermod_manager.services import framework_service as svc

RED4EXT = {
    "key": "red4ext",
    "name": "RED4ext",
    "nexus_mod_id": 2380,
    "installed": True,
    "version": "1.29.1",
    "version_known": True,
}


class _DummyGQL:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class TestFrameworksRouter:
    def test_no_key_reports_disk_state_only(self, client, make_game, monkeypatch):
        make_game(name="CP2077")
        monkeypatch.setattr(
            svc,
            "detect_frameworks",
            lambda p: [
                RED4EXT,
                {
                    "key": "redscript",
                    "name": "redscript",
                    "nexus_mod_id": 1511,
                    "installed": False,
                    "version": None,
                    "version_known": False,
                },
            ],
        )
        resp = client.get("/api/v1/games/CP2077/frameworks/")
        assert resp.status_code == 200
        data = resp.json()

        red = data[0]
        assert red["installed"] is True
        assert red["version"] == "1.29.1"
        assert red["latest_version"] is None
        assert red["outdated"] is False  # no API key → no latest lookup
        assert "cyberpunk2077/mods/2380" in red["nexus_url"]

        assert data[1]["installed"] is False
        assert data[1]["version_known"] is False

    def test_outdated_with_key(self, client, make_game, monkeypatch):
        make_game(name="CP2077")
        monkeypatch.setattr(svc, "detect_frameworks", lambda p: [RED4EXT])

        async def fake_latest(domain, gql, ids):
            return {2380: "1.30.0"}

        monkeypatch.setattr(svc, "fetch_latest_versions", fake_latest)
        monkeypatch.setattr("rippermod_manager.routers.frameworks.get_setting", lambda s, k: "KEY")
        monkeypatch.setattr("rippermod_manager.routers.frameworks.NexusGraphQLClient", _DummyGQL)

        resp = client.get("/api/v1/games/CP2077/frameworks/")
        assert resp.status_code == 200
        red = resp.json()[0]
        assert red["latest_version"] == "1.30.0"
        assert red["outdated"] is True

    def test_not_outdated_when_up_to_date(self, client, make_game, monkeypatch):
        make_game(name="CP2077")
        monkeypatch.setattr(svc, "detect_frameworks", lambda p: [RED4EXT])

        async def fake_latest(domain, gql, ids):
            return {2380: "1.29.1"}

        monkeypatch.setattr(svc, "fetch_latest_versions", fake_latest)
        monkeypatch.setattr("rippermod_manager.routers.frameworks.get_setting", lambda s, k: "KEY")
        monkeypatch.setattr("rippermod_manager.routers.frameworks.NexusGraphQLClient", _DummyGQL)

        resp = client.get("/api/v1/games/CP2077/frameworks/")
        assert resp.json()[0]["outdated"] is False
