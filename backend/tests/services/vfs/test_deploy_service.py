from pathlib import Path
from unittest.mock import patch

from rippermod_manager.models.game import Game
from rippermod_manager.services.vfs.deploy_service import pre_flight_check


def make_game(tmp_path: Path) -> Game:
    install = tmp_path / "game"
    (install / "downloaded_mods").mkdir(parents=True)
    return Game(id=1, name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(install))


def test_pre_flight_clean(tmp_path):
    g = make_game(tmp_path)
    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        r = pre_flight_check(g)
    assert r.ok is True
    assert r.game_running is False


def test_pre_flight_refuses_if_game_running(tmp_path):
    g = make_game(tmp_path)
    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=True):
        r = pre_flight_check(g)
    assert r.ok is False
    assert r.game_running is True
    assert any("running" in s.lower() for s in r.reasons)
