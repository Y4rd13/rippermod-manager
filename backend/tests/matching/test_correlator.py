from rippermod_manager.matching.correlator import (
    _categories_compatible,
    classify_group_category,
    compute_name_score,
    correlate_game_mods,
    normalize,
    token_jaccard,
)
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.mod import ModFile, ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModMeta


class TestTokenJaccard:
    def test_identical(self):
        assert token_jaccard("cyber engine tweaks", "cyber engine tweaks") == 1.0

    def test_no_overlap(self):
        assert token_jaccard("alpha beta", "gamma delta") == 0.0

    def test_partial_overlap(self):
        score = token_jaccard("cyber engine tweaks", "cyber engine")
        assert 0.0 < score < 1.0

    def test_empty_returns_zero(self):
        assert token_jaccard("", "hello") == 0.0
        assert token_jaccard("hello", "") == 0.0


class TestNormalize:
    def test_basic(self):
        assert normalize("My-Mod_Name") == "my mod name"

    def test_dots(self):
        assert normalize("v1.2.3") == "v1 2 3"

    def test_camel_case_splitting(self):
        assert normalize("EgghancedBloodFx") == "egghanced blood fx"

    def test_ordering_prefix_stripped(self):
        assert normalize("##EgghancedBloodFx") == "egghanced blood fx"

    def test_z_prefix_stripped(self):
        assert normalize("zModName") == "mod name"

    def test_z_lowercase_preserved(self):
        assert normalize("zebra") == "zebra"


class TestComputeNameScore:
    def test_exact_match(self):
        score, method = compute_name_score("enhanced weather", "enhanced weather")
        assert score == 1.0
        assert method == "exact"

    def test_substring_match(self):
        score, method = compute_name_score("weather", "enhanced weather mod")
        assert score == 0.9
        assert method == "substring"

    def test_fuzzy_match(self):
        score, method = compute_name_score("enhanced weathre", "enhanced weather")
        assert method == "fuzzy"
        assert 0.0 < score < 1.0

    def test_poor_match(self):
        score, _ = compute_name_score("alpha", "zzzzzz")
        assert score < 0.5

    def test_zero_jaccard_returns_zero(self):
        """When tokens have zero overlap, score should be 0.0 regardless of Jaro-Winkler."""
        score, method = compute_name_score("AutoLoot", "Lizzie's Braindances")
        assert score == 0.0
        assert method == "fuzzy"

    def test_no_match_for_zero_token_overlap(self):
        """Completely unrelated mod names must not correlate even with short names."""
        score, _ = compute_name_score("Quickhack", "Vehicles")
        assert score == 0.0

    def test_camel_case_vs_spaced_nexus_name(self):
        """CamelCase local name should match dash-separated Nexus name."""
        score, _method = compute_name_score("##EgghancedBloodFx", "BLOOD FX - EGGHANCED")
        # Jaccard is 1.0, Jaro-Winkler is lower due to word reordering; combined >= 0.6
        assert score >= 0.6

    def test_z_prefix_local_vs_clean_nexus(self):
        score, _method = compute_name_score("zVendorsXL", "Vendors XL")
        assert score >= 0.8


class TestCorrelateGameMods:
    def test_no_groups(self, session, make_game):
        game = make_game()
        result = correlate_game_mods(game, session)
        assert result.total_groups == 0
        assert result.matched == 0

    def test_no_downloads(self, session, make_game):
        game = make_game()
        session.add(ModGroup(game_id=game.id, display_name="MyMod"))
        session.commit()
        result = correlate_game_mods(game, session)
        assert result.total_groups == 1
        assert result.matched == 0

    def test_creates_correlation(self, session, make_game):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="Enhanced Weather")
        session.add(group)
        dl = NexusDownload(
            game_id=game.id,
            nexus_mod_id=100,
            mod_name="Enhanced Weather",
        )
        session.add(dl)
        session.commit()
        result = correlate_game_mods(game, session)
        assert result.matched == 1

    def test_skips_low_score(self, session, make_game):
        game = make_game()
        session.add(ModGroup(game_id=game.id, display_name="AAAA"))
        session.add(NexusDownload(game_id=game.id, nexus_mod_id=200, mod_name="ZZZZ"))
        session.commit()
        result = correlate_game_mods(game, session)
        assert result.matched == 0

    def test_skips_already_matched(self, session, make_game):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="CET")
        session.add(group)
        dl = NexusDownload(game_id=game.id, nexus_mod_id=300, mod_name="CET")
        session.add(dl)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id, nexus_download_id=dl.id, score=1.0, method="exact"
            )
        )
        session.commit()
        result = correlate_game_mods(game, session)
        assert result.matched == 1
        assert result.unmatched == 0

    def test_purges_stale_name_correlation(self, session, make_game):
        """Correlation becomes stale when NexusDownload name changes after sync."""
        from sqlmodel import select

        game = make_game()
        group = ModGroup(game_id=game.id, display_name="Yaiba Muramasa")
        session.add(group)
        dl = NexusDownload(
            game_id=game.id,
            nexus_mod_id=500,
            mod_name="Lizzie's Braindances",  # name updated by sync
        )
        session.add(dl)
        session.flush()
        # Stale correlation: was "exact" when dl.mod_name matched, now doesn't
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id,
                nexus_download_id=dl.id,
                score=1.0,
                method="exact",
            )
        )
        session.commit()

        result = correlate_game_mods(game, session)
        # Stale correlation purged, group now unmatched
        assert result.matched == 0
        assert result.unmatched == 1
        corrs = session.exec(select(ModNexusCorrelation)).all()
        assert len(corrs) == 0

    def test_preserves_confirmed_correlation(self, session, make_game):
        """User-confirmed correlations are never purged."""
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="CustomMod")
        session.add(group)
        dl = NexusDownload(
            game_id=game.id,
            nexus_mod_id=600,
            mod_name="Totally Different Name",
        )
        session.add(dl)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id,
                nexus_download_id=dl.id,
                score=1.0,
                method="exact",
                confirmed_by_user=True,
            )
        )
        session.commit()

        result = correlate_game_mods(game, session)
        assert result.matched == 1  # preserved

    def test_preserves_non_name_methods(self, session, make_game):
        """Correlations via filename_id, md5, file_list are never purged."""
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="SomeMod")
        session.add(group)
        dl = NexusDownload(
            game_id=game.id,
            nexus_mod_id=700,
            mod_name="Completely Unrelated",
        )
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

        result = correlate_game_mods(game, session)
        assert result.matched == 1  # preserved

    def test_popularity_tiebreaker(self, session, make_game):
        """When two candidates score within 0.05, the more endorsed one wins."""
        from sqlmodel import select

        game = make_game()
        group = ModGroup(game_id=game.id, display_name="Enhanced Combat")
        session.add(group)

        dl_low = NexusDownload(game_id=game.id, nexus_mod_id=800, mod_name="Enhanced Combat")
        dl_high = NexusDownload(game_id=game.id, nexus_mod_id=801, mod_name="Enhanced Combat")
        session.add_all([dl_low, dl_high])

        # Higher endorsements on dl_high
        session.add(
            NexusModMeta(nexus_mod_id=800, endorsement_count=10, game_domain="cyberpunk2077")
        )
        session.add(
            NexusModMeta(nexus_mod_id=801, endorsement_count=5000, game_domain="cyberpunk2077")
        )
        session.commit()

        result = correlate_game_mods(game, session)
        assert result.matched == 1

        corr = session.exec(
            select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == group.id)
        ).first()
        # The more popular one should win
        dl_matched = session.get(NexusDownload, corr.nexus_download_id)
        assert dl_matched.nexus_mod_id == 801

    def test_category_penalty_applied(self, session, make_game):
        """Scripts group should penalize asset-category Nexus mod."""
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="Combat Tweaks")
        session.add(group)
        session.flush()

        # Add .reds files to classify as "scripts"
        session.add(
            ModFile(
                mod_group_id=group.id,
                filename="combat_tweaks_system.reds",
                file_path="r6/scripts/combat_tweaks.reds",
                file_hash="h",
                file_size=100,
            )
        )

        # Script mod (compatible)
        dl_script = NexusDownload(game_id=game.id, nexus_mod_id=900, mod_name="Combat Tweaks Mod")
        # Asset mod (incompatible)
        dl_asset = NexusDownload(
            game_id=game.id, nexus_mod_id=901, mod_name="Combat Tweaks Textures"
        )
        session.add_all([dl_script, dl_asset])
        session.add(
            NexusModMeta(
                nexus_mod_id=901,
                category="models and textures",
                game_domain="cyberpunk2077",
            )
        )
        session.commit()

        result = correlate_game_mods(game, session)
        assert result.matched == 1


class TestCategoryClassification:
    def test_scripts_classification(self):
        files = [
            ModFile(filename="mod.reds", file_path="p", file_hash="h", file_size=1),
            ModFile(filename="helper.reds", file_path="p", file_hash="h", file_size=1),
        ]
        assert classify_group_category(files) == "scripts"

    def test_assets_classification(self):
        files = [
            ModFile(filename="textures.archive", file_path="p", file_hash="h", file_size=1),
        ]
        assert classify_group_category(files) == "assets"

    def test_tweaks_classification(self):
        files = [
            ModFile(filename="config.yaml", file_path="p", file_hash="h", file_size=1),
            ModFile(filename="data.xl", file_path="p", file_hash="h", file_size=1),
        ]
        assert classify_group_category(files) == "tweaks"

    def test_no_classification(self):
        files = [
            ModFile(filename="readme.txt", file_path="p", file_hash="h", file_size=1),
        ]
        assert classify_group_category(files) is None

    def test_compatible_categories(self):
        assert _categories_compatible("scripts", "gameplay") is True
        assert _categories_compatible(None, "anything") is True

    def test_incompatible_categories(self):
        assert _categories_compatible("scripts", "models and textures") is False
        assert _categories_compatible("assets", "scripts") is False
