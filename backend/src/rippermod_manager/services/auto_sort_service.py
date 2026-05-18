"""Conflict-aware automatic load-order sorting.

There is no LOOT masterlist for Cyberpunk 2077, so we cannot rely on a
community-curated rule database the way LOOT does for Bethesda titles.  Instead,
we apply a transparent heuristic: among mods that actually conflict, the mod
with the **smaller total file footprint** is treated as more selective and
wins (i.e. is placed earlier in ``modlist.txt``).  Ties are skipped and fall
back to the default ASCII order.

The service produces a set of pairwise preferences that, once applied, drive
the existing topological sort in :mod:`modlist_service`.  Auto-sort is
purely a *suggestion engine* - the user previews and explicitly accepts the
plan before any preferences are written.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from sqlmodel import Session, select

from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.models.load_order import LoadOrderPreference
from rippermod_manager.schemas.load_order import (
    AutoSortChange,
    AutoSortPreview,
    PreferencePair,
)

logger = logging.getLogger(__name__)


def _file_counts_for_mods(session: Session, mod_ids: set[int]) -> dict[int, int]:
    """Return ``mod_id -> total InstalledModFile count`` for the given mods."""
    if not mod_ids:
        return {}
    rows = session.exec(
        select(InstalledModFile.installed_mod_id).where(
            InstalledModFile.installed_mod_id.in_(mod_ids)  # type: ignore[union-attr]
        )
    ).all()
    counts: dict[int, int] = defaultdict(int)
    for mod_id in rows:
        counts[mod_id] += 1
    return counts


def _conflicting_mod_pairs(session: Session, game_id: int) -> set[tuple[int, int]]:
    """Extract distinct mod-pair IDs that share at least one archive_resource conflict.

    Pairs are returned as ``(low_id, high_id)`` so each pair appears once.
    """
    rows = session.exec(
        select(ConflictEvidence.mod_ids).where(
            ConflictEvidence.game_id == game_id,
            ConflictEvidence.kind == ConflictKind.archive_resource,
        )
    ).all()

    pairs: set[tuple[int, int]] = set()
    for raw in rows:
        if not raw:
            continue
        try:
            ids = sorted({int(x) for x in raw.split(",") if x.strip()})
        except ValueError:
            continue
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pairs.add((ids[i], ids[j]))
    return pairs


def compute_auto_sort(game: Game, session: Session) -> AutoSortPreview:
    """Produce a load-order plan based on the file-count heuristic.

    For every pair of installed mods that share an ``archive_resource`` conflict:

    - If both mods are enabled and have different file counts, the smaller one
      becomes the winner.
    - If the opposite preference already exists, it is queued for removal.
    - If the desired preference already exists, nothing is proposed.
    - Tied pairs are skipped.
    """
    pairs = _conflicting_mod_pairs(session, game.id)  # type: ignore[arg-type]
    if not pairs:
        return AutoSortPreview(
            proposed_add=[],
            proposed_remove=[],
            affected_mods=[],
            conflict_pairs_evaluated=0,
            rationale=(
                "No conflicting mods were detected - load order is already at the "
                "default ASCII order."
            ),
        )

    mod_ids: set[int] = set()
    for a, b in pairs:
        mod_ids.add(a)
        mod_ids.add(b)

    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.id.in_(mod_ids),  # type: ignore[union-attr]
            InstalledMod.game_id == game.id,
        )
    ).all()
    mod_by_id: dict[int, InstalledMod] = {m.id: m for m in mods if m.id is not None}

    file_counts = _file_counts_for_mods(session, set(mod_by_id.keys()))

    existing_prefs = session.exec(
        select(LoadOrderPreference).where(LoadOrderPreference.game_id == game.id)
    ).all()
    existing: set[tuple[int, int]] = {(p.winner_mod_id, p.loser_mod_id) for p in existing_prefs}

    proposed_add: list[PreferencePair] = []
    proposed_remove: list[PreferencePair] = []
    affected: dict[int, AutoSortChange] = {}
    evaluated = 0

    for a, b in pairs:
        mod_a = mod_by_id.get(a)
        mod_b = mod_by_id.get(b)
        if mod_a is None or mod_b is None:
            continue
        if mod_a.disabled or mod_b.disabled:
            continue

        count_a = file_counts.get(a, 0)
        count_b = file_counts.get(b, 0)
        if count_a == count_b:
            continue

        evaluated += 1
        if count_a < count_b:
            winner, loser = mod_a, mod_b
        else:
            winner, loser = mod_b, mod_a

        if (winner.id, loser.id) in existing:
            continue
        if (loser.id, winner.id) in existing:
            proposed_remove.append(
                PreferencePair(winner_mod_id=loser.id, loser_mod_id=winner.id)  # type: ignore[arg-type]
            )
        proposed_add.append(
            PreferencePair(winner_mod_id=winner.id, loser_mod_id=loser.id)  # type: ignore[arg-type]
        )

        for m in (winner, loser):
            if m.id not in affected:
                affected[m.id] = AutoSortChange(  # type: ignore[arg-type]
                    mod_id=m.id,  # type: ignore[arg-type]
                    mod_name=m.name,
                    file_count=file_counts.get(m.id, 0),  # type: ignore[arg-type]
                )

    if not proposed_add and not proposed_remove:
        rationale = (
            f"Evaluated {evaluated} conflicting mod pair(s); current order already "
            "matches the heuristic (smaller mod = wins)."
        )
    else:
        rationale = (
            f"Evaluated {evaluated} conflicting mod pair(s). The mod with the smaller "
            "total file count wins each conflict - smaller mods are typically more "
            "selective overrides and should load first."
        )

    return AutoSortPreview(
        proposed_add=proposed_add,
        proposed_remove=proposed_remove,
        affected_mods=sorted(affected.values(), key=lambda c: c.file_count),
        conflict_pairs_evaluated=evaluated,
        rationale=rationale,
    )
