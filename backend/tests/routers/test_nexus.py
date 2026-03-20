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
