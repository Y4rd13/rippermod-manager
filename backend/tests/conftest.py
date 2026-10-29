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


@pytest.fixture
def client(engine, monkeypatch):
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
