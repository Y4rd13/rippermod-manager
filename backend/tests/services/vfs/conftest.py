import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import (  # noqa: F401 — needed for SQLModel.metadata registration
    DeployJournalEntry,
    InstalledMod,
    InstalledModFile,
)


@pytest.fixture
def tmp_volume(tmp_path):
    """Two sibling dirs guaranteed same volume."""
    staging = tmp_path / "staging"
    target = tmp_path / "target"
    staging.mkdir()
    target.mkdir()
    return staging, target


skip_if_not_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="VFS primitives are Windows-only",
)


@pytest.fixture
def in_memory_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def in_memory_session(in_memory_engine):
    with Session(in_memory_engine) as s:
        yield s


@pytest.fixture
def sample_game(in_memory_session, tmp_path):
    install = tmp_path / "game"
    (install / "downloaded_mods").mkdir(parents=True)
    g = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(install))
    in_memory_session.add(g)
    in_memory_session.commit()
    in_memory_session.refresh(g)
    return g
