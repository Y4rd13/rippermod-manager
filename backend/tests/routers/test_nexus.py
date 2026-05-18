import httpx
import respx
from sqlmodel import Session

from rippermod_manager.models.nexus import NexusModMeta, NexusModRequirement
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


class TestModDetailRequirements:
    """Coverage for the is_installed / installed_mod_id fields on requirements.

    The cross-reference logic in `mod_detail` looks up InstalledMod rows for the
    same game and marks requirements whose required_mod_id matches an installed
    nexus_mod_id. This is the Full-edition test counterpart to TestModSummary
    on the nexus-compliant branch (which uses a separate /summary endpoint).
    """

    def test_requirement_marked_installed(self, client, session, respx_mock):
        from sqlmodel import select

        from rippermod_manager.models.game import Game
        from rippermod_manager.models.install import InstalledMod

        _seed_game(client)
        meta = _seed_mod_meta(session, mod_id=42, description="non-empty")
        session.add(
            NexusModRequirement(
                nexus_mod_id=42,
                required_mod_id=100,
                mod_name="Required Mod",
                is_reverse=False,
            )
        )
        game = session.exec(select(Game).where(Game.domain_name == "cyberpunk2077")).one()
        installed = InstalledMod(game_id=game.id, name="Required Mod", nexus_mod_id=100)
        session.add(installed)
        session.commit()
        session.refresh(installed)
        # Anchor meta so we don't trip the API fetch path
        meta.requirements_fetched_at = meta.created_at
        session.add(meta)
        session.commit()

        r = client.get("/api/v1/nexus/mods/cyberpunk2077/42/detail")
        assert r.status_code == 200, r.text
        reqs = r.json()["requirements"]
        assert len(reqs) == 1
        assert reqs[0]["is_installed"] is True
        assert reqs[0]["installed_mod_id"] == installed.id
