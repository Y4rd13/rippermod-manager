"""With Cyberpunk running, uninstall, toggle and profile load answer 409 and change nothing."""

import zipfile

import pytest
from sqlmodel import Session

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.services import install_service
from rippermod_manager.services.install_service import install_mod

RUNNING_MESSAGE = "Cyberpunk 2077 is running, close it first."


@pytest.fixture
def installed_mod_fixture(tmp_path, client, engine):
    """A game on disk with one installed mod; returns (game_name, mod_id, game_dir)."""
    game_dir = tmp_path / "game"
    staging = game_dir / "downloaded_mods"
    staging.mkdir(parents=True)
    archive = staging / "Guarded.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("mods/guarded.txt", b"data")
    with Session(engine) as s:
        g = Game(name="RunningGame", domain_name="cyberpunk2077", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()
        s.refresh(g)
        game_name = g.name
        result = install_mod(g, archive, s)
        mod_id = result.installed_mod_id
    return game_name, mod_id, game_dir


@pytest.fixture
def game_running(monkeypatch):
    monkeypatch.setattr(install_service, "is_game_running", lambda *a, **k: True)


def _mod(engine, mod_id: int) -> InstalledMod | None:
    with Session(engine) as s:
        return s.get(InstalledMod, mod_id)


def test_toggle_endpoint_returns_409_when_game_running(
    client, engine, installed_mod_fixture, game_running
):
    game_name, mod_id, game_dir = installed_mod_fixture

    r = client.patch(f"/api/v1/games/{game_name}/install/installed/{mod_id}/toggle")

    assert r.status_code == 409
    assert r.json()["detail"] == RUNNING_MESSAGE
    assert _mod(engine, mod_id).disabled is False
    assert (game_dir / "mods" / "guarded.txt").exists()


def test_uninstall_endpoint_returns_409_when_game_running(
    client, engine, installed_mod_fixture, game_running
):
    game_name, mod_id, game_dir = installed_mod_fixture

    r = client.delete(f"/api/v1/games/{game_name}/install/installed/{mod_id}")

    assert r.status_code == 409
    assert r.json()["detail"] == RUNNING_MESSAGE
    assert _mod(engine, mod_id) is not None
    assert (game_dir / "mods" / "guarded.txt").exists()


def test_profile_load_endpoint_returns_409_when_game_running(
    client, engine, installed_mod_fixture, monkeypatch
):
    game_name, _mod_id, _game_dir = installed_mod_fixture
    created = client.post(f"/api/v1/games/{game_name}/profiles/", json={"name": "P"})
    assert created.status_code in (200, 201), created.text
    profile_id = created.json()["id"]
    monkeypatch.setattr(install_service, "is_game_running", lambda *a, **k: True)

    r = client.post(f"/api/v1/games/{game_name}/profiles/{profile_id}/load")

    assert r.status_code == 409
    assert r.json()["detail"] == RUNNING_MESSAGE


def test_inbox_resolve_returns_409_when_game_running(
    client, engine, installed_mod_fixture, game_running
):
    """The conflicts inbox reinstall calls uninstall_mod: it must also answer 409."""
    game_name, mod_id, _game_dir = installed_mod_fixture

    r = client.post(
        f"/api/v1/games/{game_name}/conflicts/inbox/{mod_id}/resolve",
        json={"action": "reinstall"},
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == RUNNING_MESSAGE
    assert _mod(engine, mod_id) is not None
