from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.services.collection_matcher import match_by_collections


def _make_gql_mock(collections=None, revision_return=None):
    mock = AsyncMock()
    mock.__aenter__.return_value = mock
    mock.search_collections.return_value = collections or []
    mock.get_collection_revision.return_value = revision_return or {}
    return mock


class TestMatchByCollections:
    @pytest.mark.asyncio
    async def test_no_correlated_mods_returns_zero(self, session, make_game):
        game = make_game()
        session.add(ModGroup(game_id=game.id, display_name="SomeMod"))
        session.commit()
        result = await match_by_collections(game, "key", session)
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_insufficient_overlap_skipped(self, session, make_game):
        """Collection with < 3 common mods should not trigger matching."""
        game = make_game()
        # Create 2 correlated mods (below threshold of 3)
        for i in range(2):
            g = ModGroup(game_id=game.id, display_name=f"Mod{i}")
            session.add(g)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=100 + i, mod_name=f"Mod{i}")
            session.add(dl)
            session.flush()
            session.add(
                ModNexusCorrelation(
                    mod_group_id=g.id,
                    nexus_download_id=dl.id,
                    score=1.0,
                    method="exact",
                )
            )
        session.add(ModGroup(game_id=game.id, display_name="Unmatched"))
        session.commit()

        result = await match_by_collections(game, "key", session)
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_collection_match_creates_correlation(self, session, make_game):
        game = make_game()
        # Create 3 correlated mods (meets threshold)
        for i in range(3):
            g = ModGroup(game_id=game.id, display_name=f"CorrelatedMod{i}")
            session.add(g)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=100 + i, mod_name=f"CorrelatedMod{i}")
            session.add(dl)
            session.flush()
            session.add(
                ModNexusCorrelation(
                    mod_group_id=g.id,
                    nexus_download_id=dl.id,
                    score=1.0,
                    method="exact",
                )
            )

        # Add unmatched group that should match collection mod
        unmatched = ModGroup(game_id=game.id, display_name="Cyber Engine Tweaks")
        session.add(unmatched)
        session.commit()

        collections = [
            {
                "slug": "test-coll",
                "name": "Test Collection",
                "endorsements": 500,
                "latestPublishedRevision": {"revisionNumber": 1},
            }
        ]
        revision = {
            "revisionNumber": 1,
            "modFiles": [
                {"file": {"mod": {"modId": 100, "name": "CorrelatedMod0"}}, "optional": False},
                {"file": {"mod": {"modId": 101, "name": "CorrelatedMod1"}}, "optional": False},
                {"file": {"mod": {"modId": 102, "name": "CorrelatedMod2"}}, "optional": False},
                {"file": {"mod": {"modId": 999, "name": "Cyber Engine Tweaks"}}, "optional": False},
            ],
        }

        with patch("rippermod_manager.services.collection_matcher.NexusGraphQLClient") as mock_cls:
            mock_cls.return_value = _make_gql_mock(
                collections=collections, revision_return=revision
            )
            result = await match_by_collections(game, "key", session)

        assert result.matched == 1
        corrs = session.exec(
            select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == unmatched.id)
        ).all()
        assert len(corrs) == 1
        assert corrs[0].method == "collection"
        assert corrs[0].score == 0.85
