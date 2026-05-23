"""Tests for the framework monitor endpoint."""

from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusModMeta
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

    def test_offline_outdated_from_cache(self, client, session, make_game, monkeypatch):
        make_game(name="CP2077")
        monkeypatch.setattr(svc, "detect_frameworks", lambda p: [RED4EXT])
        # No API key → live lookup skipped; cached meta supplies the latest version.
        session.add(NexusModMeta(nexus_mod_id=2380, version="1.30.0"))
        session.commit()

        red = client.get("/api/v1/games/CP2077/frameworks/").json()[0]
        assert red["latest_version"] == "1.30.0"
        assert red["latest_is_cached"] is True
        assert red["outdated"] is True

    def test_live_version_wins_over_cache(self, client, session, make_game, monkeypatch):
        make_game(name="CP2077")
        monkeypatch.setattr(svc, "detect_frameworks", lambda p: [RED4EXT])
        session.add(NexusModMeta(nexus_mod_id=2380, version="1.29.5"))  # stale cache
        session.commit()

        async def fake_latest(domain, gql, ids):
            return {2380: "1.30.0"}

        monkeypatch.setattr(svc, "fetch_latest_versions", fake_latest)
        monkeypatch.setattr("rippermod_manager.routers.frameworks.get_setting", lambda s, k: "KEY")
        monkeypatch.setattr("rippermod_manager.routers.frameworks.NexusGraphQLClient", _DummyGQL)

        red = client.get("/api/v1/games/CP2077/frameworks/").json()[0]
        assert red["latest_version"] == "1.30.0"  # live, not the cached 1.29.5
        assert red["latest_is_cached"] is False
        assert red["outdated"] is True

    def test_graphql_failure_falls_back_to_cache(self, client, session, make_game, monkeypatch):
        make_game(name="CP2077")
        monkeypatch.setattr(svc, "detect_frameworks", lambda p: [RED4EXT])
        session.add(NexusModMeta(nexus_mod_id=2380, version="1.30.0"))
        session.commit()

        async def fake_latest(domain, gql, ids):
            return {}  # best-effort lookup returns {} on any Nexus/HTTP error

        monkeypatch.setattr(svc, "fetch_latest_versions", fake_latest)
        monkeypatch.setattr("rippermod_manager.routers.frameworks.get_setting", lambda s, k: "KEY")
        monkeypatch.setattr("rippermod_manager.routers.frameworks.NexusGraphQLClient", _DummyGQL)

        resp = client.get("/api/v1/games/CP2077/frameworks/")
        assert resp.status_code == 200
        red = resp.json()[0]
        assert red["latest_version"] == "1.30.0"  # cache fallback, no 500
        assert red["latest_is_cached"] is True
        assert red["outdated"] is True

    def test_manager_status_disabled_vs_deploy_pending(
        self, client, session, make_game, monkeypatch
    ):
        game = make_game(name="CP2077")
        # Marker absent on disk for both; the manager state distinguishes them.
        monkeypatch.setattr(
            svc,
            "detect_frameworks",
            lambda p: [
                {
                    "key": "cet",
                    "name": "CET",
                    "nexus_mod_id": 107,
                    "installed": False,
                    "version": None,
                    "version_known": False,
                },
                {
                    "key": "tweakxl",
                    "name": "TweakXL",
                    "nexus_mod_id": 4197,
                    "installed": False,
                    "version": None,
                    "version_known": False,
                },
            ],
        )
        session.add(InstalledMod(game_id=game.id, name="CET", nexus_mod_id=107, disabled=True))
        session.add(
            InstalledMod(game_id=game.id, name="TweakXL", nexus_mod_id=4197, disabled=False)
        )
        session.commit()

        data = {d["key"]: d for d in client.get("/api/v1/games/CP2077/frameworks/").json()}
        assert data["cet"]["manager_status"] == "disabled"
        assert data["cet"]["installed"] is False
        assert data["tweakxl"]["manager_status"] == "deploy_pending"
