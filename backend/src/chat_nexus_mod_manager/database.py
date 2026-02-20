import logging
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine, text

from chat_nexus_mod_manager.config import settings

logger = logging.getLogger(__name__)

settings.db_path.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)


def _migrate_missing_columns() -> None:
    """Add columns introduced after initial schema creation."""
    migrations: list[tuple[str, str, str]] = [
        (
            "nexus_mod_meta",
            "picture_url",
            "ALTER TABLE nexus_mod_meta ADD COLUMN picture_url TEXT DEFAULT ''",
        ),
    ]
    with Session(engine) as session:
        for table, column, ddl in migrations:
            # table name from hardcoded migrations list, not user input
            rows = session.exec(text(f"PRAGMA table_info({table})")).all()  # type: ignore[arg-type]
            col_names = {r[1] for r in rows}
            if column not in col_names:
                logger.info("Migrating: adding %s.%s", table, column)
                session.exec(text(ddl))  # type: ignore[arg-type]
        session.commit()


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_missing_columns()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
