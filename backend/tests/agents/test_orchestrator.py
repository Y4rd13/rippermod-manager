import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rippermod_manager.agents.orchestrator import (
    _generate_suggestions,
    check_mod_conflicts,
    get_nexus_mod_info,
    list_all_games,
    search_local_mods,
)
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.models.mod import ModFile, ModGroup
from rippermod_manager.models.nexus import NexusModMeta


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


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


class TestCheckModConflicts:
    def test_game_not_found(self, session):
        result = check_mod_conflicts.invoke({"game_name": "NoSuchGame"})
        assert "not found" in result

    def test_no_conflicts(self, session, make_game, tmp_path):
        game = make_game(install_path=str(tmp_path / "game"))
        game_dir = Path(game.install_path)
        game_dir.mkdir(parents=True, exist_ok=True)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()

        _make_zip(staging / "A.zip", {"archive/pc/mod/a.archive": b"a"})
        mod = InstalledMod(
            game_id=game.id,
            name="A",
            source_archive="A.zip",
        )
        session.add(mod)
        session.flush()
        session.add(
            InstalledModFile(
                installed_mod_id=mod.id,
                relative_path="archive/pc/mod/a.archive",
            )
        )
        session.commit()

        result = check_mod_conflicts.invoke({"game_name": game.name})
        assert "No conflicts" in result

    def test_detects_conflicts(self, session, make_game, tmp_path):
        game = make_game(install_path=str(tmp_path / "game"))
        game_dir = Path(game.install_path)
        game_dir.mkdir(parents=True, exist_ok=True)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()

        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = t1 + timedelta(hours=1)

        _make_zip(staging / "A.zip", {"archive/pc/mod/shared.archive": b"a"})
        mod_a = InstalledMod(
            game_id=game.id,
            name="ModA",
            source_archive="A.zip",
            installed_at=t1,
        )
        session.add(mod_a)
        session.flush()
        session.add(
            InstalledModFile(
                installed_mod_id=mod_a.id,
                relative_path="archive/pc/mod/shared.archive",
            )
        )

        _make_zip(staging / "B.zip", {"archive/pc/mod/shared.archive": b"b"})
        mod_b = InstalledMod(
            game_id=game.id,
            name="ModB",
            source_archive="B.zip",
            installed_at=t2,
        )
        session.add(mod_b)
        session.flush()
        session.add(
            InstalledModFile(
                installed_mod_id=mod_b.id,
                relative_path="archive/pc/mod/shared.archive",
            )
        )
        session.commit()

        result = check_mod_conflicts.invoke({"game_name": game.name})
        assert "conflict" in result.lower()
        assert "ModA" in result
        assert "ModB" in result

    def test_pairwise_mode(self, session, make_game, tmp_path):
        game = make_game(install_path=str(tmp_path / "game"))
        game_dir = Path(game.install_path)
        game_dir.mkdir(parents=True, exist_ok=True)
        staging = game_dir / "downloaded_mods"
        staging.mkdir()

        _make_zip(staging / "A.zip", {"archive/pc/mod/x.archive": b"a"})
        mod_a = InstalledMod(
            game_id=game.id,
            name="AlphaMod",
            source_archive="A.zip",
        )
        session.add(mod_a)
        session.flush()
        session.add(
            InstalledModFile(
                installed_mod_id=mod_a.id,
                relative_path="archive/pc/mod/x.archive",
            )
        )

        _make_zip(staging / "B.zip", {"archive/pc/mod/x.archive": b"b"})
        mod_b = InstalledMod(
            game_id=game.id,
            name="BetaMod",
            source_archive="B.zip",
        )
        session.add(mod_b)
        session.flush()
        session.add(
            InstalledModFile(
                installed_mod_id=mod_b.id,
                relative_path="archive/pc/mod/x.archive",
            )
        )
        session.commit()

        result = check_mod_conflicts.invoke(
            {
                "game_name": game.name,
                "mod_a_name": "Alpha",
                "mod_b_name": "Beta",
            }
        )
        assert "AlphaMod" in result
        assert "BetaMod" in result
        assert "x.archive" in result.lower() or "conflict" in result.lower()
