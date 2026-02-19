from chat_nexus_mod_manager.models.mod import ModFile, ModGroup
from chat_nexus_mod_manager.vector.indexer import index_mod_groups
from chat_nexus_mod_manager.vector.search import (
    search_all_semantic,
    semantic_search,
)


class TestSemanticSearch:
    def test_empty_collections(self, session, patched_chroma):
        results = semantic_search("test query")
        assert results == []

    def test_returns_results_after_index(self, session, make_game, patched_chroma):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="Enhanced Weather", confidence=0.9)
        session.add(group)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group.id,
                file_path="mods/weather.archive",
                filename="weather.archive",
                source_folder="mods",
            )
        )
        session.commit()
        index_mod_groups(game.id)
        results = semantic_search("weather", collections=["mod_groups"])
        assert len(results) >= 1

    def test_has_required_fields(self, session, make_game, patched_chroma):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="TestMod")
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
        index_mod_groups(game.id)
        results = semantic_search("test", collections=["mod_groups"])
        assert len(results) >= 1
        r = results[0]
        assert "collection" in r
        assert "document" in r
        assert "distance" in r
        assert "type" in r

    def test_respects_n_results(self, session, make_game, patched_chroma):
        game = make_game()
        for i in range(5):
            g = ModGroup(game_id=game.id, display_name=f"Mod {i}")
            session.add(g)
            session.flush()
            session.add(
                ModFile(
                    mod_group_id=g.id,
                    file_path=f"mods/mod{i}.archive",
                    filename=f"mod{i}.archive",
                    source_folder="mods",
                )
            )
        session.commit()
        index_mod_groups(game.id)
        results = semantic_search("mod", collections=["mod_groups"], n_results=2)
        assert len(results) <= 2

    def test_sorted_by_distance(self, session, make_game, patched_chroma):
        game = make_game()
        for name in ["Weather Enhanced", "Texture Pack"]:
            g = ModGroup(game_id=game.id, display_name=name)
            session.add(g)
            session.flush()
            session.add(
                ModFile(
                    mod_group_id=g.id,
                    file_path=f"mods/{name}.archive",
                    filename=f"{name}.archive",
                    source_folder="mods",
                )
            )
        session.commit()
        index_mod_groups(game.id)
        results = semantic_search("weather", collections=["mod_groups"])
        if len(results) >= 2:
            dists = [float(r["distance"]) for r in results]
            assert dists == sorted(dists)


class TestSearchAllSemantic:
    def test_returns_string(self, session, patched_chroma):
        result = search_all_semantic("test query")
        assert isinstance(result, str)
        assert "No relevant results" in result
