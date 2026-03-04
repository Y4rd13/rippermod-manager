from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.mod import ModFile, ModGroup
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.nexus.client import NexusRateLimitError
from rippermod_manager.services.file_content_matcher import (
    _pick_distinctive_file,
    match_by_file_contents,
)


class TestPickDistinctiveFile:
    def test_prefers_archive_files(self):
        files = [
            ModFile(filename="config.yaml", file_path="p", file_hash="h", file_size=1),
            ModFile(filename="my_awesome_mod.archive", file_path="p", file_hash="h", file_size=1),
        ]
        result = _pick_distinctive_file(files)
        assert result == "my_awesome_mod"

    def test_skips_generic_names(self):
        files = [
            ModFile(filename="readme.txt", file_path="p", file_hash="h", file_size=1),
            ModFile(filename="init.lua", file_path="p", file_hash="h", file_size=1),
        ]
        result = _pick_distinctive_file(files)
        assert result is None

    def test_skips_short_names(self):
        files = [
            ModFile(filename="mod.reds", file_path="p", file_hash="h", file_size=1),
        ]
        result = _pick_distinctive_file(files)
        assert result is None

    def test_returns_longest_stem(self):
        files = [
            ModFile(filename="CoolModTextures.archive", file_path="p", file_hash="h", file_size=1),
        ]
        result = _pick_distinctive_file(files)
        assert result == "coolmodtextures"


class TestMatchByFileContents:
    def _make_gql_mock(self, search_results=None, get_mod_return=None):
        mock = AsyncMock()
        mock.__aenter__.return_value = mock
        mock.search_file_contents.return_value = search_results or []
        mock.get_mod.return_value = get_mod_return or {
            "modId": 42,
            "name": "TestMod",
            "uid": "uid42",
        }
        return mock

    @pytest.mark.asyncio
    async def test_match_single_mod_creates_correlation(self, session, make_game):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="CustomTextures")
        session.add(group)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group.id,
                filename="my_custom_textures.archive",
                file_path="mods/my_custom_textures.archive",
                file_hash="abc",
                file_size=100,
            )
        )
        session.commit()

        search_results = [
            {
                "filePath": "my_custom_textures.archive",
                "fileSize": 100,
                "modFile": {
                    "fileId": 1,
                    "name": "file.zip",
                    "mod": {"modId": 42, "name": "Custom Textures Mod"},
                },
            }
        ]

        with patch(
            "rippermod_manager.services.file_content_matcher.NexusGraphQLClient"
        ) as mock_cls:
            mock_cls.return_value = self._make_gql_mock(
                search_results=search_results,
                get_mod_return={"modId": 42, "name": "Custom Textures Mod", "uid": "uid42"},
            )
            result = await match_by_file_contents(game, "key", session)

        assert result.matched == 1
        corrs = session.exec(
            select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == group.id)
        ).all()
        assert len(corrs) == 1
        assert corrs[0].method == "file_content"

    @pytest.mark.asyncio
    async def test_ambiguous_results_no_match(self, session, make_game):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="AmbiguousMod")
        session.add(group)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group.id,
                filename="ambiguous_textures.archive",
                file_path="mods/ambiguous.archive",
                file_hash="h",
                file_size=100,
            )
        )
        session.commit()

        search_results = [
            {
                "filePath": "f1",
                "fileSize": 100,
                "modFile": {
                    "fileId": 1,
                    "name": "a",
                    "mod": {"modId": 42, "name": "Mod A"},
                },
            },
            {
                "filePath": "f2",
                "fileSize": 200,
                "modFile": {
                    "fileId": 2,
                    "name": "b",
                    "mod": {"modId": 99, "name": "Mod B"},
                },
            },
        ]

        with patch(
            "rippermod_manager.services.file_content_matcher.NexusGraphQLClient"
        ) as mock_cls:
            mock_cls.return_value = self._make_gql_mock(search_results=search_results)
            result = await match_by_file_contents(game, "key", session)

        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_generic_filenames_skipped(self, session, make_game):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="GenericMod")
        session.add(group)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group.id,
                filename="init.lua",
                file_path="mods/init.lua",
                file_hash="h",
                file_size=50,
            )
        )
        session.commit()

        with patch(
            "rippermod_manager.services.file_content_matcher.NexusGraphQLClient"
        ) as mock_cls:
            mock_cls.return_value = self._make_gql_mock()
            result = await match_by_file_contents(game, "key", session)

        assert result.groups_searched == 0
        assert result.skipped_generic == 1

    @pytest.mark.asyncio
    async def test_rate_limit_stops_gracefully(self, session, make_game):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="RateLimitMod")
        session.add(group)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group.id,
                filename="ratelimit_textures.archive",
                file_path="mods/ratelimit.archive",
                file_hash="h",
                file_size=100,
            )
        )
        session.commit()

        mock = AsyncMock()
        mock.__aenter__.return_value = mock
        mock.search_file_contents.side_effect = NexusRateLimitError(0, 0, "")

        with patch(
            "rippermod_manager.services.file_content_matcher.NexusGraphQLClient"
        ) as mock_cls:
            mock_cls.return_value = mock
            result = await match_by_file_contents(game, "key", session)

        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_max_searches_respected(self, session, make_game):
        game = make_game()
        for i in range(5):
            g = ModGroup(game_id=game.id, display_name=f"Mod{i}")
            session.add(g)
            session.flush()
            session.add(
                ModFile(
                    mod_group_id=g.id,
                    filename=f"distinctive_file_{i}.archive",
                    file_path=f"mods/f{i}.archive",
                    file_hash="h",
                    file_size=100,
                )
            )
        session.commit()

        mock = AsyncMock()
        mock.__aenter__.return_value = mock
        mock.search_file_contents.return_value = []

        with patch(
            "rippermod_manager.services.file_content_matcher.NexusGraphQLClient"
        ) as mock_cls:
            mock_cls.return_value = mock
            result = await match_by_file_contents(game, "key", session, max_searches=2)

        assert mock.search_file_contents.call_count == 2
        assert result.groups_searched == 2

    @pytest.mark.asyncio
    async def test_skips_group_with_existing_correlation(self, session, make_game):
        """Group that already has a correlation from a prior phase should be skipped."""
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="AlreadyMatched")
        session.add(group)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group.id,
                filename="already_matched_mod.archive",
                file_path="mods/already_matched_mod.archive",
                file_hash="abc",
                file_size=100,
            )
        )
        dl = NexusDownload(game_id=game.id, nexus_mod_id=99, mod_name="Prior Match")
        session.add(dl)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id,
                nexus_download_id=dl.id,
                score=0.95,
                method="filename_id",
            )
        )
        session.commit()

        with patch(
            "rippermod_manager.services.file_content_matcher.NexusGraphQLClient"
        ) as mock_cls:
            mock_cls.return_value = self._make_gql_mock()
            result = await match_by_file_contents(game, "key", session)

        # Group already matched — should not be searched
        assert result.groups_searched == 0
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_cross_game_correlations_ignored(self, session, make_game):
        """Correlations from another game should not affect unmatched-group calculation."""
        game_a = make_game(name="GameA", domain_name="gamea")
        game_b = make_game(name="GameB", domain_name="gameb")

        # Group in game_a — correlated
        group_a = ModGroup(game_id=game_a.id, display_name="ModA")
        session.add(group_a)
        dl_a = NexusDownload(game_id=game_a.id, nexus_mod_id=50, mod_name="ModA")
        session.add(dl_a)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group_a.id,
                nexus_download_id=dl_a.id,
                score=1.0,
                method="exact",
            )
        )

        # Group in game_b — unmatched, should be searched
        group_b = ModGroup(game_id=game_b.id, display_name="ModB")
        session.add(group_b)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group_b.id,
                filename="distinctive_mod_b.archive",
                file_path="mods/distinctive_mod_b.archive",
                file_hash="h",
                file_size=100,
            )
        )
        session.commit()

        mock = AsyncMock()
        mock.__aenter__.return_value = mock
        mock.search_file_contents.return_value = []

        with patch(
            "rippermod_manager.services.file_content_matcher.NexusGraphQLClient"
        ) as mock_cls:
            mock_cls.return_value = mock
            result = await match_by_file_contents(game_b, "key", session)

        # game_a's correlation should NOT cause game_b's group to appear "matched"
        assert result.groups_searched == 1
