import pytest
from sqlmodel import Session

from rippermod_manager.models.game import Game, GameModPath


@pytest.fixture
def adopt_game(tmp_path, client, engine):
    """Create a game on disk + DB and return (game_name, game_dir)."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "downloaded_mods").mkdir()
    with Session(engine) as s:
        g = Game(name="AdoptGame", domain_name="cyberpunk2077", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="archive/pc/mod"))
        s.commit()
    return "AdoptGame", game_dir


def test_adopt_endpoint_adopts_files(client, adopt_game, monkeypatch):
    from rippermod_manager.services import adopt_service

    monkeypatch.setattr(adopt_service, "is_game_running", lambda *a, **k: False)
    game_name, game_dir = adopt_game
    f = game_dir / "archive" / "pc" / "mod" / "x.archive"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")

    resp = client.post(
        f"/api/v1/games/{game_name}/install/adopt",
        json={"groups": [{"name": "X", "relative_paths": ["archive/pc/mod/x.archive"]}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["adopted_mods"] == 1
    assert body["adopted_files"] == 1
    assert body["game_running"] is False


def test_adopt_endpoint_404_for_unknown_game(client):
    resp = client.post(
        "/api/v1/games/NoSuchGame/install/adopt",
        json={"groups": []},
    )
    assert resp.status_code == 404
