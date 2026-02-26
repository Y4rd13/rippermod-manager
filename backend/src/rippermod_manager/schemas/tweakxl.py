"""Pydantic schemas for TweakXL tweak conflict detection."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class TweakOperation(StrEnum):
    """The type of operation a tweak line performs on a record key."""

    SET = "set"
    APPEND = "append"
    REMOVE = "remove"


class ConflictSeverity(StrEnum):
    """How severe a conflict between two tweak operations is."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TweakEntry(BaseModel):
    """A single parsed operation from a tweak file."""

    key: str
    operation: TweakOperation
    value: str
    source_file: str
    mod_id: str


class ConflictEvidence(BaseModel):
    """Evidence of a semantic conflict between two tweak entries from different mods."""

    key: str
    severity: ConflictSeverity
    description: str
    entry_a: TweakEntry
    entry_b: TweakEntry


class TweakConflictResult(BaseModel):
    """Aggregate result of analyzing tweak conflicts across multiple mods."""

    total_entries: int
    total_conflicts: int
    conflicts: list[ConflictEvidence]
    mods_analyzed: list[str]
