"""Core conflict domain types for archive-level resource collision detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ConflictType(StrEnum):
    """Classification of the conflict mechanism."""

    ARCHIVE_HASH = "archive_hash"


class ConflictSeverity(StrEnum):
    """How impactful the conflict is for a given archive."""

    CRITICAL = "critical"  # All entries lose — mod has zero effect
    HIGH = "high"  # >50% of entries lose
    MODERATE = "moderate"  # 1-50% of entries lose
    INFO = "info"  # Mod wins all conflicting entries


@dataclass(frozen=True, slots=True)
class ConflictEvidence:
    """A single detected conflict between two archive files.

    ``winner_archive`` and ``loser_archive`` are filenames (not full paths)
    since ASCII-alphabetical filename order determines the winner in
    Cyberpunk 2077's archive loading.
    """

    conflict_type: ConflictType
    resource_hash: int
    winner_archive: str
    loser_archive: str
    winner_installed_mod_id: int | None
    loser_installed_mod_id: int | None
