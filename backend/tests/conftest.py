import os
import secrets
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

# The API token must be in place before the app (and its cached token) loads.
API_TOKEN = secrets.token_hex(32)
os.environ["RMM_API_TOKEN"] = API_TOKEN

import rippermod_manager.models  # noqa: E402, F401 — register all tables
from rippermod_manager.database import _set_sqlite_pragma, get_session  # noqa: E402
from rippermod_manager.main import app  # noqa: E402
from rippermod_manager.models.game import Game, GameModPath  # noqa: E402


@pytest.fixture(autouse=True)
def _no_adopt_backfill_thread(monkeypatch):
    """Entering the app lifespan must not start the real adopt-archive backfill thread.

    It would share the StaticPool test engine's single connection (or, in tests that do not
    patch the engine, write to the real database). Tests that mean it call
    ``run_adopt_backfill_all_games`` directly or patch it themselves.
    """
    monkeypatch.setattr("rippermod_manager.main.run_adopt_backfill_all_games", lambda: None)


@pytest.fixture(autouse=True)
def background_requests(monkeypatch):
    """Background runners never start threads in tests; their requests are recorded.

    ``calls["redmod"]`` holds the game ids that asked for a REDmod compile and
    ``calls["conflicts"]`` those that asked for a conflict reindex. Tests that mean the
    real job call it directly (``redmod_scheduler._compile_job``, ``auto_reindex._reindex_job``).
    """
    from rippermod_manager.services.conflicts import auto_reindex
    from rippermod_manager.services.vfs import redmod_scheduler

    calls: dict[str, list[int]] = {"redmod": [], "conflicts": []}

    def _record(kind: str):
        def _request(key: int) -> bool:
            calls[kind].append(key)
            return True

        return _request

    monkeypatch.setattr(redmod_scheduler._runner, "request", _record("redmod"))
    monkeypatch.setattr(redmod_scheduler, "_last", {})
    monkeypatch.setattr(auto_reindex._runner, "request", _record("conflicts"))
    return calls


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(eng, "connect", _set_sqlite_pragma)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine, monkeypatch):
    monkeypatch.setattr("rippermod_manager.database.engine", engine)
    with Session(engine) as sess:
        yield sess


def make_cp_install(root) -> str:
    """Create a fake Cyberpunk 2077 install (just its exe) at *root* and return its path.

    ``POST /api/v1/games/`` refuses an install path without the game executable.
    """
    exe_dir = root / "bin" / "x64"
    exe_dir.mkdir(parents=True, exist_ok=True)
    (exe_dir / "Cyberpunk2077.exe").write_bytes(b"MZ")
    return str(root)


@pytest.fixture
def client(engine, monkeypatch, tmp_path_factory):
    monkeypatch.setattr("rippermod_manager.database.engine", engine)

    def _override_session() -> Generator[Session, None, None]:
        with Session(engine) as sess:
            yield sess

    app.dependency_overrides[get_session] = _override_session
    # TestClient sends ``Host: testserver`` by default, which the Host allowlist refuses.
    with TestClient(
        app,
        base_url="http://127.0.0.1:8425",
        headers={"X-RMM-Token": API_TOKEN},
        raise_server_exceptions=False,
    ) as tc:
        # A valid install path for tests that create games through the API.
        tc.cp_install = make_cp_install(tmp_path_factory.mktemp("cp-install"))  # type: ignore[attr-defined]
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def make_game(session):
    def _make(
        name: str = "Cyberpunk 2077",
        domain_name: str = "cyberpunk2077",
        install_path: str = "/games/cp2077",
        mod_paths: list[str] | None = None,
    ) -> Game:
        game = Game(
            name=name,
            domain_name=domain_name,
            install_path=install_path,
        )
        session.add(game)
        session.flush()
        for rel in mod_paths or ["archive/pc/mod"]:
            session.add(GameModPath(game_id=game.id, relative_path=rel))
        session.commit()
        session.refresh(game)
        _ = game.mod_paths
        return game

    return _make
