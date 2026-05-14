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
