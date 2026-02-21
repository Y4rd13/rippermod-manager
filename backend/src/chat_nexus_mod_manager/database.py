import logging
from collections.abc import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, text

from chat_nexus_mod_manager.config import settings

logger = logging.getLogger(__name__)

settings.db_path.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{settings.db_path}",
    echo=False,
    connect_args={"timeout": 30, "check_same_thread": False},
)


def _migrate_missing_columns() -> None:
    """Add columns introduced after initial schema creation."""
    migrations: list[tuple[str, str, str]] = [
        (
            "nexus_mod_meta",
            "picture_url",
            "ALTER TABLE nexus_mod_meta ADD COLUMN picture_url TEXT DEFAULT ''",
        ),
        (
            "nexus_downloads",
            "is_tracked",
            "ALTER TABLE nexus_downloads ADD COLUMN is_tracked BOOLEAN DEFAULT 0",
        ),
        (
            "nexus_downloads",
            "is_endorsed",
            "ALTER TABLE nexus_downloads ADD COLUMN is_endorsed BOOLEAN DEFAULT 0",
        ),
        (
            "nexus_mod_meta",
            "created_at",
            "ALTER TABLE nexus_mod_meta ADD COLUMN created_at TIMESTAMP",
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
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    _migrate_missing_columns()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
