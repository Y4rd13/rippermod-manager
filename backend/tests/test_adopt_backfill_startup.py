import threading
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from rippermod_manager import main
from rippermod_manager.main import run_adopt_backfill_all_games as real_backfill
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import (
    ArchiveNexusLink,
    InstalledMod,
    InstalledModFile,
)


def _game_with_unlinked_mod(session, tmp_path: Path, name: str) -> tuple[Game, InstalledMod]:
    root = tmp_path / name
    (root / "downloaded_mods").mkdir(parents=True)
    with zipfile.ZipFile(root / "downloaded_mods" / "X-4198-1-0.zip", "w") as zf:
        zf.writestr("archive/pc/mod/x.archive", b"x")
    game = Game(name=name, domain_name="cyberpunk2077", install_path=str(root))
    session.add(game)
    session.flush()
    session.add(ArchiveNexusLink(game_id=game.id, filename="X-4198-1-0.zip", nexus_mod_id=4198))
    mod = InstalledMod(
        game_id=game.id, name="X", staging_dir="X", source_archive="", nexus_mod_id=4198
    )
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="archive/pc/mod/x.archive",
            source_path="archive/pc/mod/x.archive",
        )
    )
    session.commit()
    return game, mod


def test_startup_backfill_links_every_game(session, tmp_path):
    _, mod1 = _game_with_unlinked_mod(session, tmp_path, "g1")
    _, mod2 = _game_with_unlinked_mod(session, tmp_path, "g2")

    real_backfill()

    session.expire_all()
    assert session.get(InstalledMod, mod1.id).source_archive == "X-4198-1-0.zip"
    assert session.get(InstalledMod, mod2.id).source_archive == "X-4198-1-0.zip"


def test_startup_backfill_failure_in_one_game_does_not_stop_the_next(
    session, tmp_path, monkeypatch
):
    game1, mod1 = _game_with_unlinked_mod(session, tmp_path, "g1")
    _, mod2 = _game_with_unlinked_mod(session, tmp_path, "g2")
    from rippermod_manager.services import install_service

    real = install_service.backfill_adopted_archives

    def flaky(game, sess):
        if game.id == game1.id:
            raise RuntimeError("boom")
        return real(game, sess)

    monkeypatch.setattr(install_service, "backfill_adopted_archives", flaky)

    real_backfill()

    session.expire_all()
    assert session.get(InstalledMod, mod1.id).source_archive == ""
    assert session.get(InstalledMod, mod2.id).source_archive == "X-4198-1-0.zip"


def test_lifespan_does_not_wait_for_the_backfill(engine, monkeypatch):
    monkeypatch.setattr("rippermod_manager.database.engine", engine)
    started = threading.Event()
    release = threading.Event()
    # Safety net: a lifespan that blocked on the backfill would otherwise hang the suite.
    guard = threading.Timer(10, release.set)
    guard.start()

    def blocking_backfill() -> None:
        started.set()
        release.wait()

    monkeypatch.setattr(main, "run_adopt_backfill_all_games", blocking_backfill)
    try:
        with TestClient(main.app):
            assert started.wait(5), "backfill thread never started"
            assert not release.is_set(), "lifespan waited for the backfill"
        # Leaving the lifespan (shutdown) completed while the backfill was still running.
        assert not release.is_set()
    finally:
        release.set()
        guard.cancel()


def test_tests_do_not_run_the_real_backfill_thread_unless_they_opt_in(client):
    # conftest stubs it for every test: on the shared StaticPool test engine a real
    # thread would share the test's one connection (commit/rollback on its transaction).
    assert main.run_adopt_backfill_all_games is not real_backfill
