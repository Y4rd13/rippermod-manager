"""API response schemas for the conflicts core system."""

from __future__ import annotations

from pydantic import BaseModel

from rippermod_manager.models.conflict import ConflictKind, Severity


class ModRef(BaseModel):
    """Lightweight reference to an installed mod in a conflict."""

    id: int
    name: str


class ConflictEvidenceOut(BaseModel):
    """Single conflict evidence item for API responses."""

    id: int
    kind: ConflictKind
    severity: Severity
    key: str
    mods: list[ModRef]
    winner: ModRef | None = None
    detail: dict


class ConflictSummary(BaseModel):
    """Aggregate conflict report for a game."""

    game_name: str
    total_conflicts: int
    by_severity: dict[Severity, int]
    by_kind: dict[ConflictKind, int]
    evidence: list[ConflictEvidenceOut]


class ReindexResult(BaseModel):
    """Result of a conflict reindex operation."""

    conflicts_found: int
    by_kind: dict[ConflictKind, int]
    duration_ms: int
