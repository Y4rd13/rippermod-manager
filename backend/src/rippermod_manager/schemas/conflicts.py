"""Response models for installed-vs-installed conflict detection."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ConflictSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModConflictPair(BaseModel):
    mod_a_id: int
    mod_a_name: str
    mod_b_id: int
    mod_b_name: str
    conflicting_files: list[str]
    severity: ConflictSeverity
    winner: str


class SkippedMod(BaseModel):
    mod_id: int
    mod_name: str
    reason: str


class InstalledConflictsResult(BaseModel):
    game_name: str
    total_mods_checked: int
    conflict_pairs: list[ModConflictPair]
    skipped_mods: list[SkippedMod]


class PairwiseConflictResult(BaseModel):
    mod_a_id: int
    mod_a_name: str
    mod_b_id: int
    mod_b_name: str
    conflicting_files: list[str]
    severity: ConflictSeverity | None
    winner: str | None
