"""Tests for the activity log: GET endpoint + record_activity service."""

from sqlmodel import Session

from rippermod_manager.models.game import Game
from rippermod_manager.services import activity_service
from rippermod_manager.services.activity_service import record_activity


def _make_game(session: Session, name: str, domain: str) -> Game:
    game = Game(name=name, domain_name=domain, install_path="/games/x")
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


class TestActivityLog:
    def test_records_and_lists_newest_first(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            record_activity(s, game_id=game.id, action="install", target="ModA", detail="3 files")
            record_activity(s, game_id=game.id, action="disable", target="ModB")

        resp = client.get("/api/v1/games/Cyberpunk 2077/activity/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # newest first
        assert data[0]["action"] == "disable"
        assert data[0]["target"] == "ModB"
        assert data[1]["action"] == "install"
        assert data[1]["detail"] == "3 files"

    def test_scoped_per_game(self, client, engine):
        with Session(engine) as s:
            g1 = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            g2 = _make_game(s, "Skyrim", "skyrimspecialedition")
            record_activity(s, game_id=g1.id, action="install", target="CP Mod")
            record_activity(s, game_id=g2.id, action="install", target="SK Mod")

        resp = client.get("/api/v1/games/Cyberpunk 2077/activity/")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["target"] == "CP Mod"

    def test_limit_clamped(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            for i in range(5):
                record_activity(s, game_id=game.id, action="install", target=f"Mod{i}")

        resp = client.get("/api/v1/games/Cyberpunk 2077/activity/?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_404_unknown_game(self, client):
        resp = client.get("/api/v1/games/Nonexistent/activity/")
        assert resp.status_code == 404

    def test_prune_caps_entries(self, client, engine, monkeypatch):
        monkeypatch.setattr(activity_service, "MAX_ENTRIES_PER_GAME", 5)
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            for i in range(8):
                record_activity(s, game_id=game.id, action="install", target=f"Mod{i}")

        resp = client.get("/api/v1/games/Cyberpunk 2077/activity/?limit=1000")
        data = resp.json()
        assert len(data) == 5  # pruned to cap
        assert data[0]["target"] == "Mod7"  # newest survives
        assert data[-1]["target"] == "Mod3"  # Mod0..2 pruned
