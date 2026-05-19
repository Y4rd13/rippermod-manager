"""Tests for _migrate_missing_columns() idempotency and correctness."""

from unittest.mock import patch

from sqlalchemy import event  # used via @event.listens_for in helpers
from sqlmodel import create_engine, text
from sqlmodel.pool import StaticPool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OLD_INSTALLED_MODS_DDL = """
CREATE TABLE installed_mods (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    install_path TEXT NOT NULL DEFAULT '',
    install_order INTEGER NOT NULL DEFAULT 0,
    conflict_dismissed INTEGER NOT NULL DEFAULT 0
)
"""

_OLD_INSTALLED_MOD_FILES_DDL = """
CREATE TABLE installed_mod_files (
    id INTEGER PRIMARY KEY,
    installed_mod_id INTEGER,
    relative_path TEXT
)
"""


def _make_old_engine():
    """Return an in-memory SQLite engine with the pre-VFS installed_mods schema."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    with eng.connect() as conn:
        # Create only the tables we care about for this test.
        # installed_mods deliberately omits staging_dir, deployed, deploy_drift.
        conn.execute(text(_OLD_INSTALLED_MODS_DDL))
        conn.commit()
    return eng


def _make_old_engine_with_mod_files():
    """Return an in-memory SQLite engine with pre-VFS installed_mod_files schema."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    with eng.connect() as conn:
        conn.execute(text(_OLD_INSTALLED_MOD_FILES_DDL))
        conn.commit()
    return eng


def _get_column_names(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).all()
    return {r[1] for r in rows}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVFSColumnMigration:
    """Task 1.2 — VFS columns added to installed_mods via _migrate_missing_columns."""

    def test_new_columns_absent_before_migration(self):
        eng = _make_old_engine()
        cols = _get_column_names(eng, "installed_mods")
        assert "staging_dir" not in cols
        assert "deployed" not in cols
        assert "deploy_drift" not in cols

    def test_migration_adds_staging_dir(self):
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_old_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()

        cols = _get_column_names(eng, "installed_mods")
        assert "staging_dir" in cols, "staging_dir column not created by migration"

    def test_migration_adds_deployed(self):
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_old_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()

        cols = _get_column_names(eng, "installed_mods")
        assert "deployed" in cols, "deployed column not created by migration"

    def test_migration_adds_deploy_drift(self):
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_old_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()

        cols = _get_column_names(eng, "installed_mods")
        assert "deploy_drift" in cols, "deploy_drift column not created by migration"

    def test_migration_is_idempotent(self):
        """Running _migrate_missing_columns twice must not raise."""
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_old_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()
            _migrate_missing_columns()  # should be a no-op, not an error

        cols = _get_column_names(eng, "installed_mods")
        assert {"staging_dir", "deployed", "deploy_drift"}.issubset(cols)

    def test_column_defaults(self):
        """New columns must have the correct SQLite DEFAULT values."""
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_old_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()

        with eng.connect() as conn:
            rows = conn.execute(text("PRAGMA table_info(installed_mods)")).all()

        # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
        info = {r[1]: {"type": r[2], "notnull": r[3], "dflt_value": r[4]} for r in rows}

        assert info["staging_dir"]["type"].upper().startswith("TEXT")
        assert info["staging_dir"]["dflt_value"] == "''"

        assert info["deployed"]["type"].upper() == "BOOLEAN"
        assert info["deployed"]["dflt_value"] == "0"

        assert info["deploy_drift"]["type"].upper() == "BOOLEAN"
        assert info["deploy_drift"]["dflt_value"] == "0"

    def test_migration_adds_installed_mod_files_vfs_columns(self):
        """source_path and link_kind must be added to installed_mod_files."""
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_old_engine_with_mod_files()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()

        cols = _get_column_names(eng, "installed_mod_files")
        assert "source_path" in cols, "source_path column not created by migration"
        assert "link_kind" in cols, "link_kind column not created by migration"

    def test_migration_adds_installed_mod_files_vfs_columns_is_idempotent(self):
        """Running _migrate_missing_columns twice on installed_mod_files must not raise."""
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_old_engine_with_mod_files()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()
            _migrate_missing_columns()  # should be a no-op, not an error

        cols = _get_column_names(eng, "installed_mod_files")
        assert {"source_path", "link_kind"}.issubset(cols)


class TestDeployJournalTableCreation:
    """Task 1.4 — deploy_journal table auto-created via SQLModel.metadata.create_all."""

    def test_deploy_journal_table_is_created_on_init(self):
        from sqlmodel import SQLModel, create_engine
        from sqlmodel.pool import StaticPool

        # Import the model so SQLModel's metadata registry includes it before create_all.
        from rippermod_manager.models import install  # noqa: F401
        from rippermod_manager.models.install import DeployJournalEntry  # noqa: F401

        eng = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(eng)

        with eng.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = {row[0] for row in result}

        assert "deploy_journal" in tables


# ---------------------------------------------------------------------------
# Collections — #222 PR B
# ---------------------------------------------------------------------------


_OLD_INSTALLED_MODS_PRE_COLLECTIONS_DDL = """
CREATE TABLE installed_mods (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    source_archive TEXT DEFAULT '',
    nexus_mod_id INTEGER,
    nexus_file_id INTEGER,
    installed_version TEXT DEFAULT '',
    disabled INTEGER DEFAULT 0,
    conflict_dismissed INTEGER DEFAULT 0,
    staging_dir TEXT DEFAULT '',
    deployed INTEGER DEFAULT 0,
    deploy_drift INTEGER DEFAULT 0
)
"""

_OLD_DOWNLOAD_JOBS_PRE_COLLECTIONS_DDL = """
CREATE TABLE download_jobs (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL,
    nexus_mod_id INTEGER NOT NULL,
    nexus_file_id INTEGER NOT NULL,
    file_name TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    progress_bytes INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    error TEXT DEFAULT ''
)
"""


def _make_pre_collections_engine():
    """In-memory engine that mimics an existing user's DB before Collections shipped."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    with eng.connect() as conn:
        conn.execute(text(_OLD_INSTALLED_MODS_PRE_COLLECTIONS_DDL))
        conn.execute(text(_OLD_DOWNLOAD_JOBS_PRE_COLLECTIONS_DDL))
        conn.commit()
    return eng


class TestCollectionColumnMigration:
    """#222 PR B — new columns on installed_mods + download_jobs."""

    def test_columns_absent_before_migration(self):
        eng = _make_pre_collections_engine()
        im_cols = _get_column_names(eng, "installed_mods")
        dj_cols = _get_column_names(eng, "download_jobs")
        assert "installed_collection_id" not in im_cols
        assert "collection_phase" not in im_cols
        assert "is_optional" not in im_cols
        assert "installed_collection_id" not in dj_cols

    def test_migration_adds_installed_mods_collection_columns(self):
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_pre_collections_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()

        cols = _get_column_names(eng, "installed_mods")
        assert {"installed_collection_id", "collection_phase", "is_optional"}.issubset(cols)

    def test_migration_adds_download_jobs_collection_column(self):
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_pre_collections_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()

        cols = _get_column_names(eng, "download_jobs")
        assert "installed_collection_id" in cols

    def test_collection_columns_defaults(self):
        """New columns must default to NULL / 0 so existing rows don't break."""
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_pre_collections_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()

        with eng.connect() as conn:
            rows = conn.execute(text("PRAGMA table_info(installed_mods)")).all()
        info = {r[1]: {"type": r[2], "notnull": r[3], "dflt_value": r[4]} for r in rows}

        # installed_collection_id is a nullable FK column with no default
        assert info["installed_collection_id"]["type"].upper() == "INTEGER"
        assert info["installed_collection_id"]["notnull"] == 0
        # collection_phase + is_optional default to 0 (no order, not optional)
        assert info["collection_phase"]["dflt_value"] == "0"
        assert info["is_optional"]["dflt_value"] == "0"

    def test_migration_is_idempotent(self):
        from rippermod_manager.database import _migrate_missing_columns

        eng = _make_pre_collections_engine()
        with patch("rippermod_manager.database.engine", eng):
            _migrate_missing_columns()
            _migrate_missing_columns()

        cols = _get_column_names(eng, "installed_mods")
        assert {"installed_collection_id", "collection_phase", "is_optional"}.issubset(cols)


class TestInstalledCollectionsTableCreation:
    """#222 PR B — installed_collections table auto-created via metadata.create_all."""

    def test_table_is_created_on_init(self):
        from sqlmodel import SQLModel, create_engine
        from sqlmodel.pool import StaticPool

        # Registers InstalledCollection with SQLModel's metadata.
        from rippermod_manager.models import collection  # noqa: F401
        from rippermod_manager.models.collection import InstalledCollection  # noqa: F401

        eng = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(eng)

        with eng.connect() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).all()
            }

        assert "installed_collections" in tables

    def test_table_has_expected_columns(self):
        from sqlmodel import SQLModel, create_engine
        from sqlmodel.pool import StaticPool

        from rippermod_manager.models.collection import InstalledCollection  # noqa: F401

        eng = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(eng)

        cols = _get_column_names(eng, "installed_collections")
        expected = {
            "id",
            "game_id",
            "slug",
            "revision_id",
            "revision_number",
            "latest_known_revision_number",
            "collection_name",
            "author_name",
            "summary",
            "tile_image_url",
            "status",
            "started_at",
            "finished_at",
            "error",
            "total_mods",
            "completed_mods",
            "failed_mods",
            "skipped_mods",
        }
        assert expected.issubset(cols), f"missing columns: {expected - cols}"

    def test_unique_index_on_game_and_slug(self):
        """Re-installing the same collection slug for a game updates the
        existing row rather than creating a duplicate."""
        from sqlmodel import SQLModel, create_engine
        from sqlmodel.pool import StaticPool

        from rippermod_manager.database import _migrate_unique_indexes
        from rippermod_manager.models.collection import InstalledCollection  # noqa: F401

        eng = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(eng, "connect")
        def _enable_fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        SQLModel.metadata.create_all(eng)
        # The migration helper needs an `app_settings` table because it also
        # runs the keyring migration — but only _migrate_unique_indexes does
        # the index work, so call that directly.
        with patch("rippermod_manager.database.engine", eng):
            _migrate_unique_indexes()

        with eng.connect() as conn:
            indexes = {
                r[1] for r in conn.execute(text("PRAGMA index_list(installed_collections)")).all()
            }
        assert "uq_installed_collections_game_slug" in indexes
