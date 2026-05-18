import json

import httpx
import respx
from sqlmodel import Session

from rippermod_manager.models.nexus import NexusDownload, NexusModMeta, NexusModRequirement
from rippermod_manager.nexus.client import BASE_URL


def _seed_game(client):
    client.post(
        "/api/v1/games/",
        json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
    )


def _seed_mod_meta(session: Session, mod_id: int = 42, **overrides) -> NexusModMeta:
    defaults = dict(
        nexus_mod_id=mod_id,
        game_domain="cyberpunk2077",
        name="Test Mod",
        author="Author",
        version="1.0",
        category="Gameplay",
    )
    defaults.update(overrides)
    meta = NexusModMeta(**defaults)
    session.add(meta)
    session.commit()
    session.refresh(meta)
    return meta


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


class TestModSummary:
    def test_not_found_no_key(self, client):
        r = client.get("/api/v1/nexus/mods/9999/summary")
        assert r.status_code == 404

    def test_cached_meta_returns_summary(self, client, session):
        _seed_game(client)
        _seed_mod_meta(session, mod_id=42)

        r = client.get("/api/v1/nexus/mods/42/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["nexus_mod_id"] == 42
        assert data["name"] == "Test Mod"
        assert data["author"] == "Author"
        assert data["version"] == "1.0"
        assert data["nexus_url"] == "https://www.nexusmods.com/cyberpunk2077/mods/42"
        assert data["is_tracked"] is False
        assert data["is_endorsed"] is False
        assert data["requirements"] == []
        assert data["dlc_requirements"] == []

    def test_includes_requirements(self, client, session):
        _seed_game(client)
        _seed_mod_meta(session, mod_id=42)
        session.add(
            NexusModRequirement(
                nexus_mod_id=42,
                required_mod_id=100,
                mod_name="Required Mod",
                url="https://nexusmods.com/cyberpunk2077/mods/100",
                is_reverse=False,
            )
        )
        session.commit()

        r = client.get("/api/v1/nexus/mods/42/summary")
        assert r.status_code == 200
        data = r.json()
        assert len(data["requirements"]) == 1
        assert data["requirements"][0]["mod_name"] == "Required Mod"
        assert data["requirements"][0]["required_mod_id"] == 100
        assert data["requirements"][0]["is_installed"] is False
        assert data["requirements"][0]["installed_mod_id"] is None

    def test_requirement_marked_installed(self, client, session):
        """When the required mod is already an InstalledMod for the same game,
        the response should set is_installed=True and expose installed_mod_id."""
        from rippermod_manager.models.game import Game
        from rippermod_manager.models.install import InstalledMod

        _seed_game(client)
        _seed_mod_meta(session, mod_id=42)
        session.add(
            NexusModRequirement(
                nexus_mod_id=42,
                required_mod_id=100,
                mod_name="Required Mod",
                is_reverse=False,
            )
        )
        from sqlmodel import select

        game = session.exec(select(Game).where(Game.domain_name == "cyberpunk2077")).one()
        installed = InstalledMod(game_id=game.id, name="Required Mod", nexus_mod_id=100)
        session.add(installed)
        session.commit()
        session.refresh(installed)

        r = client.get("/api/v1/nexus/mods/42/summary")
        assert r.status_code == 200
        req = r.json()["requirements"][0]
        assert req["is_installed"] is True
        assert req["installed_mod_id"] == installed.id

    def test_excludes_reverse_requirements(self, client, session):
        _seed_game(client)
        _seed_mod_meta(session, mod_id=42)
        session.add(
            NexusModRequirement(
                nexus_mod_id=42, required_mod_id=200, mod_name="Dependent", is_reverse=True
            )
        )
        session.commit()

        r = client.get("/api/v1/nexus/mods/42/summary")
        assert r.status_code == 200
        assert len(r.json()["requirements"]) == 0

    def test_includes_dlc_requirements(self, client, session):
        _seed_game(client)
        dlc = [{"expansion_name": "Phantom Liberty", "expansion_id": "ep1", "notes": ""}]
        _seed_mod_meta(session, mod_id=42, dlc_requirements=json.dumps(dlc))

        r = client.get("/api/v1/nexus/mods/42/summary")
        assert r.status_code == 200
        data = r.json()
        assert len(data["dlc_requirements"]) == 1
        assert data["dlc_requirements"][0]["expansion_name"] == "Phantom Liberty"

    def test_tracked_endorsed_state(self, client, session):
        _seed_game(client)
        _seed_mod_meta(session, mod_id=42)
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        game = session.exec(select(Game)).first()
        session.add(
            NexusDownload(
                game_id=game.id,
                nexus_mod_id=42,
                mod_name="Test Mod",
                nexus_url="https://www.nexusmods.com/cyberpunk2077/mods/42",
                is_tracked=True,
                is_endorsed=True,
            )
        )
        session.commit()

        r = client.get("/api/v1/nexus/mods/42/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["is_tracked"] is True
        assert data["is_endorsed"] is True

    def test_no_content_fields_in_response(self, client, session):
        """Verify the summary endpoint does NOT return mod page content."""
        _seed_game(client)
        _seed_mod_meta(session, mod_id=42, description="Full BBCode description here")

        r = client.get("/api/v1/nexus/mods/42/summary")
        assert r.status_code == 200
        data = r.json()
        # Content replication fields must NOT be present
        assert "description" not in data
        assert "changelogs" not in data
        assert "files" not in data
        assert "mod_downloads" not in data
        # Metadata fields ARE present (policy-compliant)
        assert "picture_url" in data
        assert "name" in data

    def test_fresh_refreshes_version_from_nexus(self, client, session):
        """``?fresh=true`` must re-fetch from Nexus so the cached version is
        refreshed (used by the in-app update notification)."""
        from unittest.mock import AsyncMock, patch

        _seed_game(client)
        _seed_mod_meta(session, mod_id=42, version="1.0")
        client.put(
            "/api/v1/settings/",
            json={"settings": {"nexus_api_key": "valid-key"}},
        )

        fresh_gql_response = {
            "modId": 42,
            "name": "Test Mod",
            "summary": "",
            "description": "",
            "version": "2.0",  # newer than the cached "1.0"
            "author": "Author",
            "uid": "",
            "createdAt": None,
            "updatedAt": None,
            "endorsements": 0,
            "downloads": 0,
            "pictureUrl": "",
            "category": "Gameplay",
            "status": "published",
            "modCategory": {"name": "Gameplay"},
            "modRequirements": {
                "nexusRequirements": {"nodes": []},
                "modsRequiringThisMod": {"nodes": []},
                "dlcRequirements": [],
            },
        }
        with patch(
            "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_mod",
            new=AsyncMock(return_value=fresh_gql_response),
        ):
            r = client.get("/api/v1/nexus/mods/42/summary?fresh=true")
        assert r.status_code == 200
        assert r.json()["version"] == "2.0"

    def test_fresh_falls_back_to_cache_when_nexus_unreachable(self, client, session):
        """If the GraphQL refresh fails (rate limit, network), ``?fresh=true``
        must NOT 500 — fall back to the cached row so the UI still works."""
        from unittest.mock import AsyncMock, patch

        import httpx as _httpx

        _seed_game(client)
        _seed_mod_meta(session, mod_id=42, version="1.0")
        client.put(
            "/api/v1/settings/",
            json={"settings": {"nexus_api_key": "valid-key"}},
        )

        with patch(
            "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_mod",
            new=AsyncMock(side_effect=_httpx.HTTPError("boom")),
        ):
            r = client.get("/api/v1/nexus/mods/42/summary?fresh=true")
        assert r.status_code == 200
        assert r.json()["version"] == "1.0"

    def test_fresh_falls_back_to_cache_when_no_api_key(self, client, session):
        """``?fresh=true`` with no API key must return the cached value rather
        than 404 (Nexus app users can have a cached mod but no key yet)."""
        _seed_game(client)
        _seed_mod_meta(session, mod_id=42, version="1.0")

        r = client.get("/api/v1/nexus/mods/42/summary?fresh=true")
        assert r.status_code == 200
        assert r.json()["version"] == "1.0"
