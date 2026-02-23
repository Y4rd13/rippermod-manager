import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, select

from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.mod import ModFile, ModGroup
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.services.ai_search_matcher import (
    AISearchMatch,
    ai_search_unmatched_mods,
)


@pytest.fixture
def game(session: Session) -> Game:
    g = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path="/games/cp2077")
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="archive/pc/mod"))
    session.commit()
    session.refresh(g)
    return g


def _make_group(session: Session, game: Game, name: str) -> ModGroup:
    group = ModGroup(game_id=game.id, display_name=name, confidence=0.8)
    session.add(group)
    session.flush()
    session.add(
        ModFile(
            mod_group_id=group.id,
            file_path=f"archive/pc/mod/{name.lower()}.archive",
            filename=f"{name.lower()}.archive",
            source_folder="archive/pc/mod",
        )
    )
    session.commit()
    return group


def _mock_openai_response(match: AISearchMatch) -> MagicMock:
    """Build a mock response object with output_text."""
    resp = MagicMock()
    resp.output_text = json.dumps(match.model_dump())
    return resp


class TestAISearchUnmatchedMods:
    @pytest.mark.asyncio
    async def test_no_unmatched_groups(self, session: Session, game: Game):
        result = await ai_search_unmatched_mods(game, "oai-key", "nexus-key", session)
        assert result.searched == 0
        assert result.matched == 0
        assert result.unmatched == 0

    @pytest.mark.asyncio
    async def test_successful_match(self, session: Session, game: Game):
        group = _make_group(session, game, "CoolMod")

        match = AISearchMatch(
            nexus_mod_id=12345,
            confidence=0.85,
            reasoning="Found exact match on Nexus",
            nexus_url="https://www.nexusmods.com/cyberpunk2077/mods/12345",
        )

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=_mock_openai_response(match))

        nexus_info = {"name": "Cool Mod", "version": "1.0", "author": "Author"}
        mock_nexus = AsyncMock()
        mock_nexus.get_mod_info = AsyncMock(return_value=nexus_info)
        mock_nexus.hourly_remaining = 50
        mock_nexus.__aenter__ = AsyncMock(return_value=mock_nexus)
        mock_nexus.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "rippermod_manager.services.ai_search_matcher.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "rippermod_manager.services.ai_search_matcher.NexusClient",
                return_value=mock_nexus,
            ),
        ):
            result = await ai_search_unmatched_mods(game, "oai-key", "nexus-key", session)

        assert result.searched == 1
        assert result.matched == 1
        assert result.unmatched == 0

        corr = session.exec(
            select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == group.id)
        ).first()
        assert corr is not None
        assert corr.method == "ai_search"
        assert corr.score == 0.85

    @pytest.mark.asyncio
    async def test_ai_returns_null_no_correlation(self, session: Session, game: Game):
        _make_group(session, game, "UnknownMod")

        match = AISearchMatch(
            nexus_mod_id=None,
            confidence=0.0,
            reasoning="Could not find this mod",
            nexus_url=None,
        )

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=_mock_openai_response(match))

        mock_nexus = AsyncMock()
        mock_nexus.hourly_remaining = 50
        mock_nexus.__aenter__ = AsyncMock(return_value=mock_nexus)
        mock_nexus.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "rippermod_manager.services.ai_search_matcher.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "rippermod_manager.services.ai_search_matcher.NexusClient",
                return_value=mock_nexus,
            ),
        ):
            result = await ai_search_unmatched_mods(game, "oai-key", "nexus-key", session)

        assert result.searched == 1
        assert result.matched == 0
        assert result.unmatched == 1

    @pytest.mark.asyncio
    async def test_confidence_capped_at_090(self, session: Session, game: Game):
        _make_group(session, game, "HighConfMod")

        match = AISearchMatch(
            nexus_mod_id=99999,
            confidence=0.99,
            reasoning="Very confident match",
            nexus_url="https://www.nexusmods.com/cyberpunk2077/mods/99999",
        )

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=_mock_openai_response(match))

        nexus_info = {"name": "High Conf Mod", "version": "2.0", "author": "Author"}
        mock_nexus = AsyncMock()
        mock_nexus.get_mod_info = AsyncMock(return_value=nexus_info)
        mock_nexus.hourly_remaining = 50
        mock_nexus.__aenter__ = AsyncMock(return_value=mock_nexus)
        mock_nexus.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "rippermod_manager.services.ai_search_matcher.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "rippermod_manager.services.ai_search_matcher.NexusClient",
                return_value=mock_nexus,
            ),
        ):
            result = await ai_search_unmatched_mods(game, "oai-key", "nexus-key", session)

        assert result.matched == 1
        corr = session.exec(select(ModNexusCorrelation)).first()
        assert corr is not None
        assert corr.score == 0.90

    @pytest.mark.asyncio
    async def test_skips_already_matched_groups(self, session: Session, game: Game):
        group = _make_group(session, game, "AlreadyMatched")

        dl = NexusDownload(
            game_id=game.id,
            nexus_mod_id=111,
            mod_name="Already Matched",
            nexus_url="https://www.nexusmods.com/cyberpunk2077/mods/111",
        )
        session.add(dl)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id,
                nexus_download_id=dl.id,
                score=0.9,
                method="correlator",
            )
        )
        session.commit()

        result = await ai_search_unmatched_mods(game, "oai-key", "nexus-key", session)
        assert result.searched == 0
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_openai_error_graceful_continue(self, session: Session, game: Game):
        _make_group(session, game, "ErrorMod")

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(side_effect=RuntimeError("API error"))

        mock_nexus = AsyncMock()
        mock_nexus.hourly_remaining = 50
        mock_nexus.__aenter__ = AsyncMock(return_value=mock_nexus)
        mock_nexus.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "rippermod_manager.services.ai_search_matcher.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "rippermod_manager.services.ai_search_matcher.NexusClient",
                return_value=mock_nexus,
            ),
        ):
            result = await ai_search_unmatched_mods(game, "oai-key", "nexus-key", session)

        assert result.searched == 1
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_rate_limit_stops_enrichment(self, session: Session, game: Game):
        _make_group(session, game, "RateLimitMod")

        match = AISearchMatch(
            nexus_mod_id=55555,
            confidence=0.80,
            reasoning="Found match",
            nexus_url="https://www.nexusmods.com/cyberpunk2077/mods/55555",
        )

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=_mock_openai_response(match))

        mock_nexus = AsyncMock()
        mock_nexus.get_mod_info = AsyncMock()
        mock_nexus.hourly_remaining = 3  # Below threshold of 5
        mock_nexus.__aenter__ = AsyncMock(return_value=mock_nexus)
        mock_nexus.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "rippermod_manager.services.ai_search_matcher.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "rippermod_manager.services.ai_search_matcher.NexusClient",
                return_value=mock_nexus,
            ),
        ):
            result = await ai_search_unmatched_mods(game, "oai-key", "nexus-key", session)

        assert result.matched == 0
        mock_nexus.get_mod_info.assert_not_called()
