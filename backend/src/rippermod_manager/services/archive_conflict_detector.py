"""Post-install .archive conflict detector.

Queries the archive_entry_index table for resource hash collisions,
determines winners by ASCII-alphabetical filename order (Cyberpunk 2077's
archive load order), and emits ConflictEvidence rows.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind, Severity

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ArchiveConflictSummary:
    """Aggregated conflict report for a single archive file."""

    archive_filename: str
    installed_mod_id: int | None
    total_entries: int
    winning_entries: int
    losing_entries: int
    conflicting_archives: tuple[str, ...]
    severity: Severity


def detect_archive_conflicts(
    session: Session,
    game_id: int,
) -> list[ConflictEvidence]:
    """Detect all resource hash collisions among indexed .archive files.

    Returns one ``ConflictEvidence`` per conflicting resource hash,
    sorted deterministically by key.  Each evidence records all
    participating mod IDs and the winner.
    """
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
        seen: dict[str, ArchiveEntryIndex] = {}
        for entry in entries:
            if entry.archive_filename not in seen:
                seen[entry.archive_filename] = entry

        sorted_archives = sorted(seen.items(), key=lambda kv: kv[0])
        winner_name, winner_entry = sorted_archives[0]
        loser_entries = sorted_archives[1:]

        all_mod_ids = [
            e.installed_mod_id for _, e in sorted_archives if e.installed_mod_id is not None
        ]

        detail = {
            "winner_archive": winner_name,
            "loser_archives": [name for name, _ in loser_entries],
        }

        evidences.append(
            ConflictEvidence(
                game_id=game_id,
                kind=ConflictKind.archive_entry,
                severity=Severity.high,
                key=hex(resource_hash),
                mod_ids=",".join(str(mid) for mid in all_mod_ids),
                winner_mod_id=winner_entry.installed_mod_id,
                detail=json.dumps(detail),
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

    * **high** - >50% of entries lose (or all entries lose)
    * **medium** - 1-50% of entries lose
    * **low** - mod wins all conflicting entries
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

    wins: dict[str, set[str]] = defaultdict(set)
    losses: dict[str, set[str]] = defaultdict(set)
    conflicts_with: dict[str, set[str]] = defaultdict(set)
    mod_ids: dict[str, int | None] = {}

    for ev in evidences:
        detail = json.loads(ev.detail)
        winner_archive = detail["winner_archive"]
        loser_archives = detail["loser_archives"]

        wins[winner_archive].add(ev.key)
        for loser in loser_archives:
            losses[loser].add(ev.key)
            conflicts_with[winner_archive].add(loser)
            conflicts_with[loser].add(winner_archive)

        mod_ids.setdefault(winner_archive, ev.winner_mod_id)

    all_archives = set(wins) | set(losses)
    summaries: list[ArchiveConflictSummary] = []
    for archive in all_archives:
        total = total_counts.get(archive, 0)
        n_wins = len(wins.get(archive, set()))
        n_losses = len(losses.get(archive, set()))

        if n_losses == 0:
            severity = Severity.low
        elif total > 0 and n_losses > total * 0.5:
            severity = Severity.high
        else:
            severity = Severity.medium

        summaries.append(
            ArchiveConflictSummary(
                archive_filename=archive,
                installed_mod_id=mod_ids.get(archive),
                total_entries=total,
                winning_entries=n_wins,
                losing_entries=n_losses,
                conflicting_archives=tuple(sorted(conflicts_with.get(archive, set()))),
                severity=severity,
            )
        )

    severity_order = {Severity.high: 0, Severity.medium: 1, Severity.low: 2}
    summaries.sort(key=lambda s: (severity_order[s.severity], s.archive_filename))
    return summaries
