import contextlib
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import chat_nexus_mod_manager.models  # noqa: F401 — register all tables
from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.main import app
from chat_nexus_mod_manager.models.game import Game, GameModPath


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _safe_monkeypatch_engine(monkeypatch, engine):
    """Monkeypatch engine references, skipping modules with unavailable deps."""
    monkeypatch.setattr("chat_nexus_mod_manager.database.engine", engine)
    for module_path in (
        "chat_nexus_mod_manager.vector.indexer.engine",
        "chat_nexus_mod_manager.agents.orchestrator.engine",
    ):
        with contextlib.suppress(ImportError, AttributeError):
            monkeypatch.setattr(module_path, engine)


@pytest.fixture
def session(engine, monkeypatch):
    with Session(engine) as sess:
        _safe_monkeypatch_engine(monkeypatch, engine)
        yield sess


@pytest.fixture
def client(engine, monkeypatch):
    _safe_monkeypatch_engine(monkeypatch, engine)

    def _override_session() -> Generator[Session, None, None]:
        with Session(engine) as sess:
            yield sess

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def patched_chroma(tmp_path, monkeypatch):
    monkeypatch.setattr("chat_nexus_mod_manager.config.settings.chroma_path", tmp_path / "chroma")
    import chat_nexus_mod_manager.vector.store as store_mod

    monkeypatch.setattr(store_mod, "_client", None)
    yield
    monkeypatch.setattr(store_mod, "_client", None)


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
