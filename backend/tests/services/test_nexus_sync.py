import httpx
import pytest
import respx
from sqlmodel import select

from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.nexus.client import BASE_URL
from chat_nexus_mod_manager.services.nexus_sync import sync_nexus_history


def _setup_respx(tracked, endorsed, mod_infos):
    respx.get(f"{BASE_URL}/v1/user/tracked_mods.json").mock(
        return_value=httpx.Response(200, json=tracked)
    )
    respx.get(f"{BASE_URL}/v1/user/endorsements.json").mock(
        return_value=httpx.Response(200, json=endorsed)
    )
    for mod_id, info in mod_infos.items():
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/{mod_id}.json").mock(
            return_value=httpx.Response(200, json=info)
        )


class TestSyncNexusHistory:
    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_new_download(self, session, make_game):
        game = make_game()
        _setup_respx(
            tracked=[{"domain_name": "cyberpunk2077", "mod_id": 10}],
            endorsed=[],
            mod_infos={
                10: {
                    "name": "CoolMod",
                    "version": "1.0",
                    "summary": "A mod",
                    "author": "Auth",
                    "category_id": 5,
                    "endorsement_count": 100,
                }
            },
        )
        result = await sync_nexus_history(game, "key", session)
        assert result.tracked_mods == 1
        assert result.total_stored == 1
        dl = session.exec(select(NexusDownload)).first()
        assert dl.mod_name == "CoolMod"

    @respx.mock
    @pytest.mark.asyncio
    async def test_updates_existing(self, session, make_game):
        game = make_game()
        session.add(
            NexusDownload(
                game_id=game.id,
                nexus_mod_id=10,
                mod_name="OldName",
                version="0.9",
            )
        )
        session.commit()
        _setup_respx(
            tracked=[{"domain_name": "cyberpunk2077", "mod_id": 10}],
            endorsed=[],
            mod_infos={
                10: {
                    "name": "NewName",
                    "version": "1.0",
                    "summary": "",
                    "author": "",
                    "category_id": 0,
                    "endorsement_count": 0,
                }
            },
        )
        await sync_nexus_history(game, "key", session)
        dl = session.exec(select(NexusDownload)).first()
        assert dl.mod_name == "NewName"
        assert dl.version == "1.0"

    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_metadata(self, session, make_game):
        game = make_game()
        _setup_respx(
            tracked=[{"domain_name": "cyberpunk2077", "mod_id": 20}],
            endorsed=[],
            mod_infos={
                20: {
                    "name": "MetaMod",
                    "version": "2.0",
                    "summary": "desc",
                    "author": "me",
                    "category_id": 3,
                    "endorsement_count": 50,
                }
            },
        )
        await sync_nexus_history(game, "key", session)
        meta = session.exec(select(NexusModMeta)).first()
        assert meta.name == "MetaMod"
        assert meta.author == "me"

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_by_domain(self, session, make_game):
        game = make_game()
        _setup_respx(
            tracked=[
                {"domain_name": "cyberpunk2077", "mod_id": 10},
                {"domain_name": "skyrim", "mod_id": 99},
            ],
            endorsed=[],
            mod_infos={
                10: {
                    "name": "CP Mod",
                    "version": "1.0",
                    "summary": "",
                    "author": "",
                    "category_id": 0,
                    "endorsement_count": 0,
                }
            },
        )
        result = await sync_nexus_history(game, "key", session)
        assert result.tracked_mods == 1
        assert result.total_stored == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_mod_info_failure(self, session, make_game):
        game = make_game()
        respx.get(f"{BASE_URL}/v1/user/tracked_mods.json").mock(
            return_value=httpx.Response(200, json=[{"domain_name": "cyberpunk2077", "mod_id": 10}])
        )
        respx.get(f"{BASE_URL}/v1/user/endorsements.json").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/10.json").mock(
            return_value=httpx.Response(500)
        )
        result = await sync_nexus_history(game, "key", session)
        assert result.total_stored == 0
