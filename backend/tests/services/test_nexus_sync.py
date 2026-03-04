from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from sqlmodel import select

from rippermod_manager.models.nexus import NexusDownload, NexusModMeta
from rippermod_manager.nexus.client import BASE_URL
from rippermod_manager.services.nexus_sync import sync_nexus_history


def _setup_respx(tracked, endorsed):
    respx.get(f"{BASE_URL}/v1/user/tracked_mods.json").mock(
        return_value=httpx.Response(200, json=tracked)
    )
    respx.get(f"{BASE_URL}/v1/user/endorsements.json").mock(
        return_value=httpx.Response(200, json=endorsed)
    )


def _make_gql_mock(batch_mods_return=None, batch_mods_side_effect=None):
    mock = AsyncMock()
    mock.__aenter__.return_value = mock
    if batch_mods_side_effect:
        mock.batch_mods.side_effect = batch_mods_side_effect
    else:
        mock.batch_mods.return_value = batch_mods_return or {}
    mock.get_mod_files.return_value = []
    return mock


class TestSyncNexusHistory:
    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_new_download(self, session, make_game):
        game = make_game()
        _setup_respx(
            tracked=[{"domain_name": "cyberpunk2077", "mod_id": 10}],
            endorsed=[],
        )
        with patch("rippermod_manager.services.nexus_sync.NexusGraphQLClient") as mock_gql_cls:
            mock_gql_cls.return_value = _make_gql_mock(
                batch_mods_return={
                    10: {
                        "name": "CoolMod",
                        "version": "1.0",
                        "summary": "A mod",
                        "author": "Auth",
                        "category": "5",
                        "endorsements": 100,
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
    async def test_updates_existing_preserves_version(self, session, make_game):
        """Sync should update mod_name but preserve the discovery-time version."""
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
        )
        with patch("rippermod_manager.services.nexus_sync.NexusGraphQLClient") as mock_gql_cls:
            mock_gql_cls.return_value = _make_gql_mock(
                batch_mods_return={
                    10: {
                        "name": "NewName",
                        "version": "1.0",
                        "summary": "",
                        "author": "",
                        "category": "0",
                        "endorsements": 0,
                    }
                },
            )
            await sync_nexus_history(game, "key", session)
        dl = session.exec(select(NexusDownload)).first()
        assert dl.mod_name == "NewName"
        assert dl.version == "0.9"  # preserved, NOT overwritten to "1.0"

    @respx.mock
    @pytest.mark.asyncio
    async def test_updates_metadata_version(self, session, make_game):
        """Sync should update NexusModMeta.version to latest API value."""
        game = make_game()
        session.add(
            NexusModMeta(nexus_mod_id=10, name="OldMod", version="0.9", game_domain="cyberpunk2077")
        )
        session.commit()
        _setup_respx(
            tracked=[{"domain_name": "cyberpunk2077", "mod_id": 10}],
            endorsed=[],
        )
        with patch("rippermod_manager.services.nexus_sync.NexusGraphQLClient") as mock_gql_cls:
            mock_gql_cls.return_value = _make_gql_mock(
                batch_mods_return={
                    10: {
                        "name": "NewMod",
                        "version": "1.0",
                        "summary": "",
                        "author": "",
                        "category": "0",
                        "endorsements": 0,
                    }
                },
            )
            await sync_nexus_history(game, "key", session)
        meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == 10)).first()
        assert meta.version == "1.0"  # metadata SHOULD be updated

    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_metadata(self, session, make_game):
        game = make_game()
        _setup_respx(
            tracked=[{"domain_name": "cyberpunk2077", "mod_id": 20}],
            endorsed=[],
        )
        with patch("rippermod_manager.services.nexus_sync.NexusGraphQLClient") as mock_gql_cls:
            mock_gql_cls.return_value = _make_gql_mock(
                batch_mods_return={
                    20: {
                        "name": "MetaMod",
                        "version": "2.0",
                        "summary": "desc",
                        "author": "me",
                        "category": "3",
                        "endorsements": 50,
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
        )
        with patch("rippermod_manager.services.nexus_sync.NexusGraphQLClient") as mock_gql_cls:
            mock_gql_cls.return_value = _make_gql_mock(
                batch_mods_return={
                    10: {
                        "name": "CP Mod",
                        "version": "1.0",
                        "summary": "",
                        "author": "",
                        "category": "0",
                        "endorsements": 0,
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
        _setup_respx(
            tracked=[{"domain_name": "cyberpunk2077", "mod_id": 10}],
            endorsed=[],
        )
        with patch("rippermod_manager.services.nexus_sync.NexusGraphQLClient") as mock_gql_cls:
            mock_gql_cls.return_value = _make_gql_mock(
                batch_mods_side_effect=httpx.HTTPError("GQL batch failed"),
            )
            result = await sync_nexus_history(game, "key", session)
        assert result.total_stored == 0
