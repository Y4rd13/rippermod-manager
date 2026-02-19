from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from chat_nexus_mod_manager.config import settings

settings.db_path.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
