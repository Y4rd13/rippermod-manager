"""Response models for conflict detection and the conflicts inbox."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

# --- Installed-vs-installed conflict detection (persisted engine) ---


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


# --- Conflicts inbox (global post-install conflict visibility) ---


class InboxSeverity(StrEnum):
    critical = "critical"
    warning = "warning"
    info = "info"


class ConflictEvidence(BaseModel):
    file_path: str
    winner_mod_id: int
    winner_mod_name: str


class ModConflictSummary(BaseModel):
    mod_id: int
    mod_name: str
    source_archive: str
    total_archive_files: int
    conflict_count: int
    severity: InboxSeverity
    conflicting_mod_names: list[str]


class ModConflictDetail(BaseModel):
    mod_id: int
    mod_name: str
    source_archive: str
    total_archive_files: int
    evidence: list[ConflictEvidence]


class ConflictsOverview(BaseModel):
    total_conflicts: int
    mods_affected: int
    summaries: list[ModConflictSummary]


class ResolveRequest(BaseModel):
    action: Literal["reinstall"]


class ResolveResult(BaseModel):
    installed_mod_id: int
    files_extracted: int
    files_reclaimed: int


# --- Conflict graph visualization ---


class ConflictGraphNode(BaseModel):
    id: str
    label: str
    source_type: str
    file_count: int
    conflict_count: int
    disabled: bool = False
    nexus_mod_id: int | None = None
    picture_url: str | None = None
    resource_conflict_count: int = 0
    real_resource_count: int = 0
    identical_resource_count: int = 0


class ConflictGraphEdge(BaseModel):
    source: str
    target: str
    shared_files: list[str]
    weight: int
    resource_conflicts: int = 0
    identical_resource_count: int = 0
    real_resource_count: int = 0


class ConflictGraphResult(BaseModel):
    nodes: list[ConflictGraphNode]
    edges: list[ConflictGraphEdge]
    total_conflicts: int
