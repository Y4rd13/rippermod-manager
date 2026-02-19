from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.mod import ModFile, ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.vector.indexer import (
    index_all,
    index_correlations,
    index_mod_groups,
    index_nexus_metadata,
)


class TestIndexModGroups:
    def test_empty_returns_zero(self, session, patched_chroma):
        assert index_mod_groups() == 0

    def test_indexes_data(self, session, make_game, patched_chroma):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="TestMod", confidence=0.9)
        session.add(group)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group.id,
                file_path="mods/test.archive",
                filename="test.archive",
                source_folder="mods",
            )
        )
        session.commit()
        count = index_mod_groups(game.id)
        assert count == 1

    def test_resets_on_recall(self, session, make_game, patched_chroma):
        game = make_game()
        session.add(ModGroup(game_id=game.id, display_name="Mod1"))
        session.commit()
        index_mod_groups(game.id)
        count = index_mod_groups(game.id)
        assert count == 1


class TestIndexNexusMetadata:
    def test_empty_returns_zero(self, session, patched_chroma):
        assert index_nexus_metadata() == 0

    def test_indexes_meta(self, session, make_game, patched_chroma):
        game = make_game()
        session.add(NexusDownload(game_id=game.id, nexus_mod_id=10))
        session.add(
            NexusModMeta(
                nexus_mod_id=10,
                game_domain="cyberpunk2077",
                name="CoolMod",
                author="Auth",
            )
        )
        session.commit()
        count = index_nexus_metadata(game.id)
        assert count == 1


class TestIndexCorrelations:
    def test_indexes_correlations(self, session, make_game, patched_chroma):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="Mod")
        session.add(group)
        dl = NexusDownload(game_id=game.id, nexus_mod_id=10, mod_name="Mod")
        session.add(dl)
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id,
                nexus_download_id=dl.id,
                score=0.9,
                method="exact",
            )
        )
        session.commit()
        count = index_correlations(game.id)
        assert count == 1


class TestIndexAll:
    def test_returns_dict(self, session, make_game, patched_chroma):
        make_game()
        result = index_all()
        assert "mod_groups" in result
        assert "nexus_mods" in result
        assert "correlations" in result
