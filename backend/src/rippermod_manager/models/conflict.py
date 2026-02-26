"""Persisted conflict evidence from the conflicts core engine.

Stores the results of post-install conflict analysis across all installed mods.
Each row represents a single conflict (e.g., two mods writing the same file).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Column, Field, SQLModel, Text


class ConflictKind(StrEnum):
    """Category of conflict between mods."""

    archive_entry = "archive_entry"
    redscript_target = "redscript_target"
    tweak_key = "tweak_key"


class Severity(StrEnum):
    """Conflict severity, determined by deterministic rules per ConflictKind."""

    high = "high"
    medium = "medium"
    low = "low"


class ConflictEvidence(SQLModel, table=True):
    """A single detected conflict between two or more installed mods."""

    __tablename__ = "conflict_evidence"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    kind: ConflictKind = Field(index=True)
    severity: Severity = Field(index=True)
    key: str = Field(index=True)
    mod_ids: str = ""
    winner_mod_id: int | None = None
    detail: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
