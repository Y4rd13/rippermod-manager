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
from rippermod_manager.schemas.conflict import (
    ArchiveResourceDetailsResult,
    ResourceConflictDetail,
    ResourceConflictGroup,
)

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
    identical_count: int = 0
    real_count: int = 0


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

        # Same-mod internal override — intentional, not actionable.
        # Also covers mod-vs-unmanaged (vanilla) which is typically intentional.
        unique_mod_ids = set(all_mod_ids)
        severity = Severity.low if len(unique_mod_ids) <= 1 else Severity.high

        sha1s = {name: entry.sha1_hex for name, entry in sorted_archives if entry.sha1_hex}
        detail = {
            "winner_archive": winner_name,
            "loser_archives": [name for name, _ in loser_entries],
            "sha1s": sha1s,
        }

        evidences.append(
            ConflictEvidence(
                game_id=game_id,
                kind=ConflictKind.archive_resource,
                severity=severity,
                key=hex(resource_hash & 0xFFFFFFFFFFFFFFFF),
                mod_ids=",".join(str(mid) for mid in all_mod_ids),
                winner_mod_id=winner_entry.installed_mod_id,
                detail=json.dumps(detail),
            )
        )

    return evidences


def summarize_conflicts(
    session: Session,
    game_id: int,
    *,
    resource_hash: str | None = None,
) -> list[ArchiveConflictSummary]:
    """Produce per-archive conflict summaries with severity ratings.

    Severity is based on the ratio of losing entries to total entries
    for each archive:

    * **high** - >50% of entries lose (or all entries lose)
    * **medium** - 1-50% of entries lose
    * **low** - mod wins all conflicting entries

    If *resource_hash* is given (hex string like ``0xa4fb…``), only evidences
    whose key matches are included.
    """
    evidences = detect_archive_conflicts(session, game_id)
    if not evidences:
        return []

    if resource_hash:
        evidences = [e for e in evidences if e.key == resource_hash]
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

    # Build archive_filename → installed_mod_id mapping from index table
    archive_mod_rows = session.exec(
        select(
            ArchiveEntryIndex.archive_filename,
            ArchiveEntryIndex.installed_mod_id,
        )
        .where(ArchiveEntryIndex.game_id == game_id)
        .group_by(ArchiveEntryIndex.archive_filename, ArchiveEntryIndex.installed_mod_id)
    ).all()
    mod_ids: dict[str, int | None] = {}
    for name, mid in archive_mod_rows:
        mod_ids.setdefault(name, mid)

    wins: dict[str, set[str]] = defaultdict(set)
    losses: dict[str, set[str]] = defaultdict(set)
    conflicts_with: dict[str, set[str]] = defaultdict(set)
    # Track per-archive identical vs real conflict counts
    identical: dict[str, int] = defaultdict(int)
    real: dict[str, int] = defaultdict(int)

    for ev in evidences:
        detail = json.loads(ev.detail)
        winner_archive = detail["winner_archive"]
        loser_archives = detail["loser_archives"]
        sha1s: dict[str, str] = detail.get("sha1s", {})

        winner_sha1 = sha1s.get(winner_archive, "")

        wins[winner_archive].add(ev.key)
        for loser in loser_archives:
            losses[loser].add(ev.key)
            conflicts_with[winner_archive].add(loser)
            conflicts_with[loser].add(winner_archive)

            loser_sha1 = sha1s.get(loser, "")
            if winner_sha1 and loser_sha1:
                if winner_sha1 == loser_sha1:
                    identical[winner_archive] += 1
                    identical[loser] += 1
                else:
                    real[winner_archive] += 1
                    real[loser] += 1

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
                identical_count=identical.get(archive, 0),
                real_count=real.get(archive, 0),
            )
        )

    severity_order = {Severity.high: 0, Severity.medium: 1, Severity.low: 2}
    summaries.sort(key=lambda s: (severity_order[s.severity], s.archive_filename))
    return summaries


def get_archive_resource_details(
    session: Session,
    game_id: int,
    archive_filename: str,
) -> ArchiveResourceDetailsResult:
    """Return per-resource conflict details for a single archive.

    Groups conflicts by partner archive and classifies each resource
    as identical (cosmetic) or real based on SHA1 comparison.
    """
    evidences = session.exec(
        select(ConflictEvidence).where(
            ConflictEvidence.game_id == game_id,
            ConflictEvidence.kind == ConflictKind.archive_resource,
            ConflictEvidence.detail.contains(archive_filename),  # type: ignore[union-attr]
        )
    ).all()

    # Validate in Python (LIKE pre-filter may include false positives)
    relevant: list[tuple[str, dict]] = []
    for ev in evidences:
        try:
            detail = json.loads(ev.detail)
        except (json.JSONDecodeError, TypeError):
            continue
        winner = detail.get("winner_archive", "")
        losers = detail.get("loser_archives", [])
        if winner == archive_filename or archive_filename in losers:
            relevant.append((ev.key, detail))

    # Group by partner archive
    partner_resources: dict[str, list[ResourceConflictDetail]] = defaultdict(list)
    for resource_hash, detail in relevant:
        winner = detail.get("winner_archive", "")
        losers: list[str] = detail.get("loser_archives", [])
        sha1s: dict[str, str] = detail.get("sha1s", {})

        partners = losers if winner == archive_filename else [winner]

        winner_sha1 = sha1s.get(winner, "")

        for partner in partners:
            if partner == archive_filename:
                continue
            partner_sha1 = sha1s.get(partner, "") if winner == archive_filename else winner_sha1
            this_sha1 = sha1s.get(archive_filename, "")
            is_identical = bool(this_sha1 and partner_sha1 and this_sha1 == partner_sha1)

            unique_sha1s = set(sha1s.values()) - {""}
            severity = Severity.low if len(unique_sha1s) <= 1 else Severity.high

            partner_resources[partner].append(
                ResourceConflictDetail(
                    resource_hash=resource_hash,
                    winner_archive=winner,
                    loser_archives=losers,
                    is_identical=is_identical,
                    severity=severity,
                )
            )

    # Build groups
    groups: list[ResourceConflictGroup] = []
    for partner, resources in sorted(partner_resources.items()):
        is_winner = archive_filename.lower() < partner.lower()
        identical = sum(1 for r in resources if r.is_identical)
        real = len(resources) - identical
        groups.append(
            ResourceConflictGroup(
                partner_archive=partner,
                is_winner=is_winner,
                identical_count=identical,
                real_count=real,
                resources=resources,
            )
        )

    total = sum(len(g.resources) for g in groups)
    return ArchiveResourceDetailsResult(
        archive_filename=archive_filename,
        total_resource_conflicts=total,
        groups=groups,
    )
