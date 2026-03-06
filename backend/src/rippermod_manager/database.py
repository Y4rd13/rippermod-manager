import logging
from collections.abc import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, text

from rippermod_manager.config import settings

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
        (
            "nexus_mod_meta",
            "description",
            "ALTER TABLE nexus_mod_meta ADD COLUMN description TEXT DEFAULT ''",
        ),
        (
            "nexus_mod_meta",
            "mod_downloads",
            "ALTER TABLE nexus_mod_meta ADD COLUMN mod_downloads INTEGER DEFAULT 0",
        ),
        (
            "profiles",
            "description",
            "ALTER TABLE profiles ADD COLUMN description TEXT DEFAULT ''",
        ),
        (
            "profiles",
            "last_loaded_at",
            "ALTER TABLE profiles ADD COLUMN last_loaded_at TIMESTAMP",
        ),
        (
            "games",
            "active_profile_id",
            "ALTER TABLE games ADD COLUMN active_profile_id INTEGER",
        ),
        (
            "nexus_mod_files",
            "content_preview_link",
            "ALTER TABLE nexus_mod_files ADD COLUMN content_preview_link TEXT",
        ),
        (
            "nexus_mod_files",
            "description",
            "ALTER TABLE nexus_mod_files ADD COLUMN description TEXT",
        ),
        (
            "nexus_mod_meta",
            "files_updated_at",
            "ALTER TABLE nexus_mod_meta ADD COLUMN files_updated_at TIMESTAMP",
        ),
        (
            "installed_mods",
            "conflict_dismissed",
            "ALTER TABLE installed_mods ADD COLUMN conflict_dismissed BOOLEAN DEFAULT 0",
        ),
        (
            "nexus_mod_meta",
            "uid",
            "ALTER TABLE nexus_mod_meta ADD COLUMN uid TEXT DEFAULT ''",
        ),
        (
            "nexus_mod_meta",
            "requirements_fetched_at",
            "ALTER TABLE nexus_mod_meta ADD COLUMN requirements_fetched_at TIMESTAMP",
        ),
        (
            "nexus_mod_requirements",
            "is_reverse",
            "ALTER TABLE nexus_mod_requirements ADD COLUMN is_reverse BOOLEAN DEFAULT 0",
        ),
        (
            "nexus_mod_meta",
            "dlc_requirements",
            "ALTER TABLE nexus_mod_meta ADD COLUMN dlc_requirements TEXT DEFAULT '[]'",
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


def _migrate_unique_indexes() -> None:
    """Create unique indexes, deduplicating existing data if needed."""
    indexes: list[tuple[str, str, list[str]]] = [
        ("installed_mods", "uq_installed_mods_game_name", ["game_id", "name"]),
        (
            "load_order_preferences",
            "uq_load_order_game_winner_loser",
            ["game_id", "winner_mod_id", "loser_mod_id"],
        ),
    ]
    with Session(engine) as session:
        for table, idx_name, columns in indexes:
            existing = session.exec(text(f"PRAGMA index_list({table})")).all()  # type: ignore[arg-type]
            if any(row[1] == idx_name for row in existing):
                continue

            # Deduplicate: keep latest id per group
            cols_csv = ", ".join(columns)
            dedup_sql = (
                f"DELETE FROM {table} WHERE id NOT IN "
                f"(SELECT MAX(id) FROM {table} GROUP BY {cols_csv})"
            )
            session.exec(text(dedup_sql))  # type: ignore[arg-type]

            create_sql = f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols_csv})"
            session.exec(text(create_sql))  # type: ignore[arg-type]
            logger.info("Created unique index %s on %s(%s)", idx_name, table, cols_csv)

        # Non-unique index for reverse-dependency lookups
        session.exec(  # type: ignore[arg-type]
            text(
                "CREATE INDEX IF NOT EXISTS ix_nexus_mod_requirements_required_mod_id "
                "ON nexus_mod_requirements(required_mod_id)"
            )
        )
        session.commit()


def _migrate_secrets_to_keyring() -> None:
    """Move plaintext API keys from SQLite to OS keyring on first run."""
    from rippermod_manager.services.keyring_service import SECRET_KEYS, set_secret

    with Session(engine) as session:
        for key in SECRET_KEYS:
            row = session.exec(
                text("SELECT value FROM app_settings WHERE key = :k"),  # type: ignore[arg-type]
                params={"k": key},
            ).first()
            if row and row[0] and set_secret(key, row[0]):
                session.exec(
                    text("UPDATE app_settings SET value = '' WHERE key = :k"),  # type: ignore[arg-type]
                    params={"k": key},
                )
                logger.info("Migrated '%s' to OS keyring", key)
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
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _migrate_missing_columns()
    _migrate_unique_indexes()
    _migrate_secrets_to_keyring()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
