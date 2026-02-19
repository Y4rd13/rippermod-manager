from chat_nexus_mod_manager.agents.orchestrator import (
    _generate_suggestions,
    get_mod_details,
    list_all_games,
    search_local_mods,
    get_nexus_mod_info,
)
from chat_nexus_mod_manager.models.game import Game, GameModPath
from chat_nexus_mod_manager.models.mod import ModFile, ModGroup
from chat_nexus_mod_manager.models.nexus import NexusModMeta


class TestGenerateSuggestions:
    def test_scan_keyword(self):
        result = _generate_suggestions("scan my mods", None)
        assert any("mods" in s.lower() for s in result)

    def test_update_keyword(self):
        result = _generate_suggestions("check updates", None)
        assert any("update" in s.lower() for s in result)

    def test_with_game_name(self):
        result = _generate_suggestions("hello", "Cyberpunk 2077")
        assert any("Cyberpunk 2077" in s for s in result)

    def test_defaults(self):
        result = _generate_suggestions("hello world", None)
        assert len(result) == 3

    def test_max_3(self):
        result = _generate_suggestions("scan mods and updates", "Game")
        assert len(result) <= 3


class TestSearchLocalMods:
    def test_no_match(self, session):
        result = search_local_mods.invoke({"query": "nonexistent"})
        assert "No mods found" in result

    def test_finds_by_name(self, session, make_game):
        game = make_game()
        group = ModGroup(game_id=game.id, display_name="Weather Enhanced")
        session.add(group)
        session.flush()
        session.add(
            ModFile(
                mod_group_id=group.id,
                file_path="mods/weather.archive",
                filename="weather.archive",
            )
        )
        session.commit()
        result = search_local_mods.invoke({"query": "Weather"})
        assert "Weather Enhanced" in result


class TestListAllGames:
    def test_empty(self, session):
        result = list_all_games.invoke({})
        assert "No games" in result

    def test_with_game(self, session, make_game):
        make_game()
        result = list_all_games.invoke({})
        assert "Cyberpunk 2077" in result


class TestGetNexusModInfo:
    def test_not_found(self, session):
        result = get_nexus_mod_info.invoke({"nexus_mod_id": 999})
        assert "No cached info" in result

    def test_returns_info(self, session):
        session.add(
            NexusModMeta(
                nexus_mod_id=42,
                name="Cool Mod",
                author="Author",
                version="1.0",
                summary="A cool mod",
                endorsement_count=100,
            )
        )
        session.commit()
        result = get_nexus_mod_info.invoke({"nexus_mod_id": 42})
        assert "Cool Mod" in result
        assert "Author" in result
