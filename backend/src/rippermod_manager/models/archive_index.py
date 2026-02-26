"""SQLModel table for the archive entry index.

Stores parsed RDAR hash entries per .archive file for fast conflict
detection via SQL queries.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ArchiveEntryIndex(SQLModel, table=True):
    __tablename__ = "archive_entry_index"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    installed_mod_id: int | None = Field(default=None, foreign_key="installed_mods.id", index=True)
    archive_filename: str = Field(index=True)
    archive_relative_path: str = ""
    resource_hash: int = Field(index=True)
    sha1_hex: str = ""
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
