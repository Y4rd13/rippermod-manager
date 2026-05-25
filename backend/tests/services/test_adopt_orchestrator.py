from pathlib import Path

import pytest

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.services import adopt_service


@pytest.fixture
def game(session, tmp_path):
    d = tmp_path / "game"
    d.mkdir()
    g = Game(name="CP", domain_name="cyberpunk2077", install_path=str(d))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="archive/pc/mod"))
    session.commit()
    session.refresh(g)
    return g


def _put(game, rel, data=b"x"):
    p = Path(game.install_path) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def test_refuses_when_game_running(session, game, monkeypatch):
    monkeypatch.setattr(adopt_service, "is_game_running", lambda *a, **k: True)
    _put(game, "archive/pc/mod/a.archive")
    report = adopt_service.adopt_detected(
        game, [{"name": "A", "relative_paths": ["archive/pc/mod/a.archive"]}], session
    )
    assert report.game_running is True
    assert report.adopted_mods == 0
    # files untouched
    assert (Path(game.install_path) / "archive/pc/mod/a.archive").exists()


def test_adopts_multiple_groups(session, game, monkeypatch):
    monkeypatch.setattr(adopt_service, "is_game_running", lambda *a, **k: False)
    _put(game, "archive/pc/mod/a.archive")
    _put(game, "archive/pc/mod/b.archive")
    report = adopt_service.adopt_detected(
        game,
        [
            {"name": "A", "relative_paths": ["archive/pc/mod/a.archive"], "nexus_mod_id": 111},
            {"name": "B", "relative_paths": ["archive/pc/mod/b.archive"]},
        ],
        session,
    )
    assert report.adopted_mods == 2
    assert report.adopted_files == 2
    names = {m.name for m in session.query(InstalledMod).all()}
    assert names == {"A", "B"}


def test_continues_past_a_failing_group(session, game, monkeypatch):
    monkeypatch.setattr(adopt_service, "is_game_running", lambda *a, **k: False)
    _put(game, "archive/pc/mod/ok.archive")
    # second group has a name collision pre-created -> adopt_mod raises ValueError
    session.add(InstalledMod(game_id=game.id, name="Taken", source_archive=""))
    session.commit()
    report = adopt_service.adopt_detected(
        game,
        [
            {"name": "OK", "relative_paths": ["archive/pc/mod/ok.archive"]},
            {"name": "Taken", "relative_paths": ["archive/pc/mod/ok.archive"]},
        ],
        session,
    )
    assert report.adopted_mods == 1
    assert len(report.errors) == 1
    assert "Taken" in report.errors[0]


def test_continues_past_a_vfs_error(session, game, monkeypatch):
    # VfsError is not an OSError; the orchestrator must still catch it and keep
    # per-group isolation rather than letting it abort the remaining groups.
    from rippermod_manager.services.vfs.primitives import VfsError

    monkeypatch.setattr(adopt_service, "is_game_running", lambda *a, **k: False)
    _put(game, "archive/pc/mod/ok.archive")

    real_adopt = adopt_service.adopt_mod

    def flaky_adopt(game_, name, paths, sess, **kw):
        if name == "Bad":
            raise VfsError("hardlink boom")
        return real_adopt(game_, name, paths, sess, **kw)

    monkeypatch.setattr(adopt_service, "adopt_mod", flaky_adopt)

    report = adopt_service.adopt_detected(
        game,
        [
            {"name": "Bad", "relative_paths": ["archive/pc/mod/missing.archive"]},
            {"name": "OK", "relative_paths": ["archive/pc/mod/ok.archive"]},
        ],
        session,
    )
    assert report.adopted_mods == 1  # OK still adopted after Bad failed
    assert len(report.errors) == 1
    assert "Bad" in report.errors[0]
