"""Post-install .archive conflict detector.

Queries the archive_entry_index table for resource hash collisions,
determines winners by ASCII-alphabetical filename order (Cyberpunk 2077's
archive load order), and emits ConflictEvidence domain objects.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.conflict import ConflictEvidence, ConflictSeverity, ConflictType

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ArchiveConflictSummary:
    """Aggregated conflict report for a single archive file."""

    archive_filename: str
    installed_mod_id: int | None
    total_entries: int
    winning_entries: int
    losing_entries: int
    conflicting_archives: list[str]
    severity: ConflictSeverity


def detect_archive_conflicts(
    session: Session,
    game_id: int,
) -> list[ConflictEvidence]:
    """Detect all resource hash collisions among indexed .archive files.

    Returns one ``ConflictEvidence`` per (resource_hash, winner, loser)
    triple, sorted deterministically by (resource_hash, winner, loser).
    """
    # Find hashes that appear in more than one distinct archive
    subq = (
        select(ArchiveEntryIndex.resource_hash)
        .where(ArchiveEntryIndex.game_id == game_id)
        .group_by(ArchiveEntryIndex.resource_hash)
        .having(func.count(func.distinct(ArchiveEntryIndex.archive_filename)) > 1)
    ).subquery()

    stmt = (
        select(ArchiveEntryIndex)
        .where(
            ArchiveEntryIndex.game_id == game_id,
            ArchiveEntryIndex.resource_hash.in_(select(subq.c.resource_hash)),  # type: ignore[union-attr]
        )
        .order_by(ArchiveEntryIndex.resource_hash, ArchiveEntryIndex.archive_filename)
    )
    rows = session.exec(stmt).all()

    hash_groups: dict[int, list[ArchiveEntryIndex]] = defaultdict(list)
    for row in rows:
        hash_groups[row.resource_hash].append(row)

    evidences: list[ConflictEvidence] = []
    for resource_hash in sorted(hash_groups):
        entries = hash_groups[resource_hash]
        # Deduplicate by archive_filename
        seen: dict[str, ArchiveEntryIndex] = {}
        for entry in entries:
            if entry.archive_filename not in seen:
                seen[entry.archive_filename] = entry

        sorted_archives = sorted(seen.items(), key=lambda kv: kv[0])
        winner_name, winner_entry = sorted_archives[0]

        for loser_name, loser_entry in sorted_archives[1:]:
            evidences.append(
                ConflictEvidence(
                    conflict_type=ConflictType.ARCHIVE_HASH,
                    resource_hash=resource_hash,
                    winner_archive=winner_name,
                    loser_archive=loser_name,
                    winner_installed_mod_id=winner_entry.installed_mod_id,
                    loser_installed_mod_id=loser_entry.installed_mod_id,
                )
            )

    return evidences


def summarize_conflicts(
    session: Session,
    game_id: int,
) -> list[ArchiveConflictSummary]:
    """Produce per-archive conflict summaries with severity ratings.

    Severity is based on the ratio of losing entries to total entries
    for each archive:

    * **CRITICAL** — all entries lose (mod has zero effect)
    * **HIGH** — >50 % of entries lose
    * **MODERATE** — 1-50 % of entries lose
    * **INFO** — mod wins all conflicting entries
    """
    evidences = detect_archive_conflicts(session, game_id)
    if not evidences:
        return []

    total_counts_rows = session.exec(
        select(
            ArchiveEntryIndex.archive_filename,
            func.count(ArchiveEntryIndex.id),
        )
        .where(ArchiveEntryIndex.game_id == game_id)
        .group_by(ArchiveEntryIndex.archive_filename)
    ).all()
    total_counts: dict[str, int] = {name: count for name, count in total_counts_rows}

    wins: dict[str, set[int]] = defaultdict(set)
    losses: dict[str, set[int]] = defaultdict(set)
    conflicts_with: dict[str, set[str]] = defaultdict(set)
    mod_ids: dict[str, int | None] = {}

    for ev in evidences:
        wins[ev.winner_archive].add(ev.resource_hash)
        losses[ev.loser_archive].add(ev.resource_hash)
        conflicts_with[ev.winner_archive].add(ev.loser_archive)
        conflicts_with[ev.loser_archive].add(ev.winner_archive)
        mod_ids.setdefault(ev.winner_archive, ev.winner_installed_mod_id)
        mod_ids.setdefault(ev.loser_archive, ev.loser_installed_mod_id)

    all_archives = set(wins) | set(losses)
    summaries: list[ArchiveConflictSummary] = []
    for archive in all_archives:
        total = total_counts.get(archive, 0)
        n_wins = len(wins.get(archive, set()))
        n_losses = len(losses.get(archive, set()))

        if n_losses == 0:
            severity = ConflictSeverity.INFO
        elif total > 0 and n_losses >= total:
            severity = ConflictSeverity.CRITICAL
        elif total > 0 and n_losses > total * 0.5:
            severity = ConflictSeverity.HIGH
        else:
            severity = ConflictSeverity.MODERATE

        summaries.append(
            ArchiveConflictSummary(
                archive_filename=archive,
                installed_mod_id=mod_ids.get(archive),
                total_entries=total,
                winning_entries=n_wins,
                losing_entries=n_losses,
                conflicting_archives=sorted(conflicts_with.get(archive, set())),
                severity=severity,
            )
        )

    severity_order = {
        ConflictSeverity.CRITICAL: 0,
        ConflictSeverity.HIGH: 1,
        ConflictSeverity.MODERATE: 2,
        ConflictSeverity.INFO: 3,
    }
    summaries.sort(key=lambda s: (severity_order[s.severity], s.archive_filename))
    return summaries
