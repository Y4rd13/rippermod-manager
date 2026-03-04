import pytest
from sqlmodel import select

from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModRequirement
from rippermod_manager.services.requirement_matcher import match_by_requirements


class TestMatchByRequirements:
    @pytest.mark.asyncio
    async def test_no_requirements_returns_zero(self, session, make_game):
        game = make_game()
        session.add(ModGroup(game_id=game.id, display_name="UnmatchedMod"))
        session.commit()
        result = await match_by_requirements(game, session)
        assert result.requirements_checked == 0
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_matching_requirement_creates_correlation(self, session, make_game):
        game = make_game()
        # Create a correlated mod
        group1 = ModGroup(game_id=game.id, display_name="Main Mod")
        session.add(group1)
        dl1 = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="Main Mod")
        session.add(dl1)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group1.id,
                nexus_download_id=dl1.id,
                score=1.0,
                method="exact",
            )
        )
        # Add a requirement pointing to another mod
        session.add(
            NexusModRequirement(
                nexus_mod_id=100,
                required_mod_id=200,
                mod_name="Required Dependency",
                is_external=False,
            )
        )
        # Create unmatched group with matching name
        group2 = ModGroup(game_id=game.id, display_name="Required Dependency")
        session.add(group2)
        session.commit()

        result = await match_by_requirements(game, session)
        assert result.matched == 1

        corrs = session.exec(
            select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == group2.id)
        ).all()
        assert len(corrs) == 1
        assert corrs[0].method == "requirement"
        assert corrs[0].score == 0.92

    @pytest.mark.asyncio
    async def test_already_correlated_group_skipped(self, session, make_game):
        game = make_game()
        group1 = ModGroup(game_id=game.id, display_name="Mod A")
        group2 = ModGroup(game_id=game.id, display_name="Required Dep")
        session.add_all([group1, group2])
        dl1 = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="Mod A")
        dl2 = NexusDownload(game_id=game.id, nexus_mod_id=200, mod_name="Required Dep")
        session.add_all([dl1, dl2])
        session.flush()
        # Both groups already correlated
        session.add(
            ModNexusCorrelation(
                mod_group_id=group1.id,
                nexus_download_id=dl1.id,
                score=1.0,
                method="exact",
            )
        )
        session.add(
            ModNexusCorrelation(
                mod_group_id=group2.id,
                nexus_download_id=dl2.id,
                score=1.0,
                method="exact",
            )
        )
        session.add(
            NexusModRequirement(
                nexus_mod_id=100,
                required_mod_id=200,
                mod_name="Required Dep",
                is_external=False,
            )
        )
        session.commit()

        result = await match_by_requirements(game, session)
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_low_similarity_no_match(self, session, make_game):
        game = make_game()
        group1 = ModGroup(game_id=game.id, display_name="Main Mod")
        session.add(group1)
        dl1 = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="Main Mod")
        session.add(dl1)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group1.id,
                nexus_download_id=dl1.id,
                score=1.0,
                method="exact",
            )
        )
        session.add(
            NexusModRequirement(
                nexus_mod_id=100,
                required_mod_id=300,
                mod_name="Totally Different Name",
                is_external=False,
            )
        )
        group2 = ModGroup(game_id=game.id, display_name="Unrelated Mod")
        session.add(group2)
        session.commit()

        result = await match_by_requirements(game, session)
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_external_requirement_skipped(self, session, make_game):
        game = make_game()
        group1 = ModGroup(game_id=game.id, display_name="Main Mod")
        session.add(group1)
        dl1 = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="Main Mod")
        session.add(dl1)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group1.id,
                nexus_download_id=dl1.id,
                score=1.0,
                method="exact",
            )
        )
        session.add(
            NexusModRequirement(
                nexus_mod_id=100,
                required_mod_id=200,
                mod_name="External Dep",
                is_external=True,
            )
        )
        group2 = ModGroup(game_id=game.id, display_name="External Dep")
        session.add(group2)
        session.commit()

        result = await match_by_requirements(game, session)
        assert result.matched == 0

    @pytest.mark.asyncio
    async def test_null_required_mod_id_skipped(self, session, make_game):
        game = make_game()
        group1 = ModGroup(game_id=game.id, display_name="Main Mod")
        session.add(group1)
        dl1 = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="Main Mod")
        session.add(dl1)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group1.id,
                nexus_download_id=dl1.id,
                score=1.0,
                method="exact",
            )
        )
        session.add(
            NexusModRequirement(
                nexus_mod_id=100,
                required_mod_id=None,
                mod_name="Some Lib",
                is_external=False,
            )
        )
        group2 = ModGroup(game_id=game.id, display_name="Some Lib")
        session.add(group2)
        session.commit()

        result = await match_by_requirements(game, session)
        assert result.matched == 0
