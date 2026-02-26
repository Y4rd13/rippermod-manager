"""Contract tests for the conflicts router endpoints."""

import pytest
from sqlmodel import Session, select

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile


@pytest.fixture
def game_setup(tmp_path, client, engine):
    """Create a game via direct DB access and return its name."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    with Session(engine) as s:
        g = Game(name="ConflictsGame", domain_name="cg", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()

    return "ConflictsGame", game_dir


def _add_conflicting_mods(engine, game_name: str, paths: list[str]) -> None:
    """Add two mods that share the same files."""
    with Session(engine) as s:
        game = s.exec(select(Game).where(Game.name == game_name)).first()
        mod_a = InstalledMod(game_id=game.id, name="ModA")
        mod_b = InstalledMod(game_id=game.id, name="ModB")
        s.add_all([mod_a, mod_b])
        s.flush()
        for p in paths:
            s.add(InstalledModFile(installed_mod_id=mod_a.id, relative_path=p))
            s.add(InstalledModFile(installed_mod_id=mod_b.id, relative_path=p))
        s.commit()


class TestConflictSummary:
    def test_empty_summary(self, client, game_setup):
        game_name, _ = game_setup
        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_conflicts"] == 0
        assert data["game_name"] == "ConflictsGame"
        assert data["evidence"] == []

    def test_game_not_found(self, client):
        r = client.get("/api/v1/games/NoSuchGame/conflicts/summary")
        assert r.status_code == 404

    def test_summary_has_expected_shape(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["overlap.dll"])
        client.post(f"/api/v1/games/{game_name}/conflicts/reindex")

        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_conflicts" in data
        assert "by_severity" in data
        assert "by_kind" in data
        assert isinstance(data["evidence"], list)
        if data["evidence"]:
            ev = data["evidence"][0]
            assert "id" in ev
            assert "kind" in ev
            assert "severity" in ev
            assert "key" in ev
            assert "mods" in ev
            assert isinstance(ev["mods"], list)
            assert "id" in ev["mods"][0]
            assert "name" in ev["mods"][0]

    def test_filter_by_kind(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["shared.txt"])
        client.post(f"/api/v1/games/{game_name}/conflicts/reindex")

        r = client.get(
            f"/api/v1/games/{game_name}/conflicts/summary?kind=archive_entry"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_conflicts"] >= 1

        r2 = client.get(
            f"/api/v1/games/{game_name}/conflicts/summary?kind=redscript_target"
        )
        assert r2.status_code == 200
        assert r2.json()["total_conflicts"] == 0

    def test_filter_by_severity(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["readme.txt"])
        client.post(f"/api/v1/games/{game_name}/conflicts/reindex")

        r = client.get(
            f"/api/v1/games/{game_name}/conflicts/summary?severity=low"
        )
        assert r.status_code == 200
        assert r.json()["total_conflicts"] >= 1


class TestReindexConflicts:
    def test_reindex_returns_result(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["same.txt"])

        r = client.post(f"/api/v1/games/{game_name}/conflicts/reindex")
        assert r.status_code == 200
        data = r.json()
        assert data["conflicts_found"] >= 1
        assert "duration_ms" in data
        assert "by_kind" in data

    def test_reindex_game_not_found(self, client):
        r = client.post("/api/v1/games/Missing/conflicts/reindex")
        assert r.status_code == 404

    def test_summary_reflects_reindex(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["overlap.dll"])

        # Before reindex, summary is empty
        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary")
        assert r.json()["total_conflicts"] == 0

        # After reindex, summary has conflicts
        client.post(f"/api/v1/games/{game_name}/conflicts/reindex")
        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary")
        assert r.json()["total_conflicts"] >= 1
