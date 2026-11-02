import pytest
from sqlmodel import select

from rippermod_manager.matching.correlator import correlate_game_mods
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
        # Exact name: the score is the name score; the 0.92 floor only lifts weaker names
        assert corrs[0].score == 1.0

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

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("group_name", "required_name", "expected"),
        [
            # weak name: below the on-disk line, no lift
            ("Immersive Rippers", "Immersive Bartenders - Dogtown", 0.557),
            # close name (0.779): lifted to the floor
            ("Weather Mod", "Weather Overhaul Mod", 0.92),
        ],
    )
    async def test_requirement_boost_only_for_close_names(
        self, session, make_game, group_name, required_name, expected
    ):
        game = make_game()
        group1 = ModGroup(game_id=game.id, display_name="Main Mod")
        session.add(group1)
        dl1 = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="Main Mod")
        session.add(dl1)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group1.id, nexus_download_id=dl1.id, score=1.0, method="exact"
            )
        )
        session.add(
            NexusModRequirement(
                nexus_mod_id=100, required_mod_id=200, mod_name=required_name, is_external=False
            )
        )
        group2 = ModGroup(game_id=game.id, display_name=group_name)
        session.add(group2)
        session.commit()

        result = await match_by_requirements(game, session)
        assert result.matched == 1
        corr = session.exec(
            select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == group2.id)
        ).one()
        assert corr.score == pytest.approx(expected, abs=0.01)


class TestForwardRequirementsOnly:
    """A mod that depends on the correlated one (a translation) is not its requirement."""

    @staticmethod
    def _correlated_main(session, game):
        group = ModGroup(game_id=game.id, display_name="Main Mod")
        dl = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="Main Mod")
        session.add_all([group, dl])
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id, nexus_download_id=dl.id, score=1.0, method="exact"
            )
        )

    @staticmethod
    def _stored_requirement_match(session, game, confirmed=False):
        group = ModGroup(game_id=game.id, display_name="Anti Theft Measures Castellano")
        dl = NexusDownload(
            game_id=game.id, nexus_mod_id=200, mod_name="Anti-Theft Measures - Castellano"
        )
        session.add_all([group, dl])
        session.flush()
        corr = ModNexusCorrelation(
            mod_group_id=group.id,
            nexus_download_id=dl.id,
            score=1.0,
            method="requirement",
            confirmed_by_user=confirmed,
        )
        session.add(corr)
        session.commit()
        return corr.id

    @staticmethod
    def _requirement_matches(session):
        # The freed group is matched again by name, so look at the method, not the row id
        return session.exec(
            select(ModNexusCorrelation).where(ModNexusCorrelation.method == "requirement")
        ).all()

    @pytest.mark.asyncio
    async def test_reverse_requirement_is_not_a_candidate(self, session, make_game):
        game = make_game()
        self._correlated_main(session, game)
        session.add(
            NexusModRequirement(
                nexus_mod_id=100,
                required_mod_id=200,
                mod_name="Anti-Theft Measures - Castellano",
                is_external=False,
                is_reverse=True,
            )
        )
        session.add(ModGroup(game_id=game.id, display_name="Anti Theft Measures Castellano"))
        session.commit()

        result = await match_by_requirements(game, session)
        assert result.matched == 0

    def test_revalidate_drops_requirement_match_without_forward_row(self, session, make_game):
        game = make_game()
        self._correlated_main(session, game)
        session.add(
            NexusModRequirement(
                nexus_mod_id=100,
                required_mod_id=200,
                mod_name="Anti-Theft Measures - Castellano",
                is_reverse=True,
            )
        )
        self._stored_requirement_match(session, game)
        correlate_game_mods(game, session)
        assert not self._requirement_matches(session)

    def test_revalidate_keeps_requirement_match_with_forward_row(self, session, make_game):
        game = make_game()
        self._correlated_main(session, game)
        session.add(
            NexusModRequirement(
                nexus_mod_id=100,
                required_mod_id=200,
                mod_name="Anti-Theft Measures - Castellano",
                is_reverse=False,
            )
        )
        corr_id = self._stored_requirement_match(session, game)
        correlate_game_mods(game, session)
        assert session.get(ModNexusCorrelation, corr_id) is not None

    def test_revalidate_drops_requirement_match_when_the_requirer_is_not_correlated(
        self, session, make_game
    ):
        game = make_game()
        self._correlated_main(session, game)
        session.add(
            NexusModRequirement(
                nexus_mod_id=999,
                required_mod_id=200,
                mod_name="Anti-Theft Measures - Castellano",
                is_reverse=False,
            )
        )
        self._stored_requirement_match(session, game)
        correlate_game_mods(game, session)
        assert not self._requirement_matches(session)

    def test_revalidate_keeps_confirmed_requirement_match_without_forward_row(
        self, session, make_game
    ):
        game = make_game()
        self._correlated_main(session, game)
        corr_id = self._stored_requirement_match(session, game, confirmed=True)
        correlate_game_mods(game, session)
        assert session.get(ModNexusCorrelation, corr_id) is not None

    def test_reverse_row_name_does_not_rescue_a_requirement_match(self, session, make_game):
        """Name is poor on the download; only a reverse row carries the good name."""
        game = make_game()
        self._correlated_main(session, game)
        group = ModGroup(game_id=game.id, display_name="Weather Mod")
        dl = NexusDownload(
            game_id=game.id, nexus_mod_id=200, mod_name="Immersive Bartenders - Dogtown"
        )
        session.add_all([group, dl])
        session.flush()
        corr = ModNexusCorrelation(
            mod_group_id=group.id, nexus_download_id=dl.id, score=0.92, method="requirement"
        )
        session.add(corr)
        session.add_all(
            [
                NexusModRequirement(
                    nexus_mod_id=100,
                    required_mod_id=200,
                    mod_name="Weather Overhaul Mod",
                    is_reverse=False,
                ),
                NexusModRequirement(
                    nexus_mod_id=300,
                    required_mod_id=200,
                    mod_name="Weather Mod",
                    is_reverse=True,
                ),
            ]
        )
        session.commit()
        correlate_game_mods(game, session)
        # The forward row's name (0.779) still keeps it; the exact-name reverse row must not
        # lift the score to 1.0.
        assert session.get(ModNexusCorrelation, corr.id).score == 0.92
