"""Deterministic conflict analyzer for TweakXL tweak operations.

Compares parsed TweakEntry operations from N mods and identifies semantic
conflicts based on operation type and value combinations.
"""

from __future__ import annotations

from collections import defaultdict

from rippermod_manager.schemas.tweakxl import (
    ConflictEvidence,
    ConflictSeverity,
    TweakConflictResult,
    TweakEntry,
    TweakOperation,
)

_SEVERITY_ORDER = {
    ConflictSeverity.HIGH: 0,
    ConflictSeverity.MEDIUM: 1,
    ConflictSeverity.LOW: 2,
}


def _compare_mod_pair(
    entries_a: list[TweakEntry],
    entries_b: list[TweakEntry],
) -> list[ConflictEvidence]:
    """Compare entries from two mods on the same key and emit conflict evidence."""
    conflicts: list[ConflictEvidence] = []

    for a in entries_a:
        for b in entries_b:
            evidence = _check_pair(a, b)
            if evidence is not None:
                conflicts.append(evidence)

    return conflicts


def _check_pair(a: TweakEntry, b: TweakEntry) -> ConflictEvidence | None:
    """Apply conflict rules to a single pair of entries on the same key."""
    op_a, op_b = a.operation, b.operation

    # SET vs SET
    if op_a == TweakOperation.SET and op_b == TweakOperation.SET:
        if a.value != b.value:
            return ConflictEvidence(
                key=a.key,
                severity=ConflictSeverity.HIGH,
                description=(
                    f"Both mods set {a.key} to different values: '{a.value}' vs '{b.value}'"
                ),
                entry_a=a,
                entry_b=b,
            )
        return ConflictEvidence(
            key=a.key,
            severity=ConflictSeverity.LOW,
            description=f"Both mods set {a.key} to the same value '{a.value}' (redundant)",
            entry_a=a,
            entry_b=b,
        )

    # APPEND vs REMOVE (same value) — in either direction
    if op_a == TweakOperation.APPEND and op_b == TweakOperation.REMOVE and a.value == b.value:
        return ConflictEvidence(
            key=a.key,
            severity=ConflictSeverity.MEDIUM,
            description=(f"One mod appends '{a.value}' to {a.key} while the other removes it"),
            entry_a=a,
            entry_b=b,
        )
    if op_a == TweakOperation.REMOVE and op_b == TweakOperation.APPEND and a.value == b.value:
        return ConflictEvidence(
            key=a.key,
            severity=ConflictSeverity.MEDIUM,
            description=(f"One mod removes '{a.value}' from {a.key} while the other appends it"),
            entry_a=a,
            entry_b=b,
        )

    # SET vs APPEND / APPEND vs SET
    if op_a == TweakOperation.SET and op_b == TweakOperation.APPEND:
        return ConflictEvidence(
            key=a.key,
            severity=ConflictSeverity.MEDIUM,
            description=(
                f"One mod overwrites {a.key} while the other appends to it; "
                f"final state depends on load order"
            ),
            entry_a=a,
            entry_b=b,
        )
    if op_a == TweakOperation.APPEND and op_b == TweakOperation.SET:
        return ConflictEvidence(
            key=a.key,
            severity=ConflictSeverity.MEDIUM,
            description=(
                f"One mod appends to {a.key} while the other overwrites it; "
                f"final state depends on load order"
            ),
            entry_a=a,
            entry_b=b,
        )

    # SET vs REMOVE / REMOVE vs SET
    if op_a == TweakOperation.SET and op_b == TweakOperation.REMOVE:
        return ConflictEvidence(
            key=a.key,
            severity=ConflictSeverity.MEDIUM,
            description=(f"One mod sets {a.key} while the other removes values from it"),
            entry_a=a,
            entry_b=b,
        )
    if op_a == TweakOperation.REMOVE and op_b == TweakOperation.SET:
        return ConflictEvidence(
            key=a.key,
            severity=ConflictSeverity.MEDIUM,
            description=(f"One mod removes values from {a.key} while the other sets it"),
            entry_a=a,
            entry_b=b,
        )

    # APPEND vs APPEND, REMOVE vs REMOVE -> no conflict
    return None


def analyze_conflicts(
    mod_entries: dict[str, list[TweakEntry]],
) -> TweakConflictResult:
    """Analyze tweak entries from multiple mods and detect semantic conflicts.

    Args:
        mod_entries: Mapping from mod_id to its parsed TweakEntry list.

    Returns:
        A TweakConflictResult with all detected conflicts sorted by severity.
    """
    total_entries = sum(len(entries) for entries in mod_entries.values())

    # Index entries by normalised key
    key_index: dict[str, list[TweakEntry]] = defaultdict(list)
    for entries in mod_entries.values():
        for entry in entries:
            key_index[entry.key.lower()].append(entry)

    conflicts: list[ConflictEvidence] = []

    for entries in key_index.values():
        by_mod: dict[str, list[TweakEntry]] = defaultdict(list)
        for e in entries:
            by_mod[e.mod_id].append(e)
        if len(by_mod) < 2:
            continue

        mod_ids = sorted(by_mod)
        for i in range(len(mod_ids)):
            for j in range(i + 1, len(mod_ids)):
                conflicts.extend(_compare_mod_pair(by_mod[mod_ids[i]], by_mod[mod_ids[j]]))

    conflicts.sort(key=lambda c: (_SEVERITY_ORDER[c.severity], c.key))

    return TweakConflictResult(
        total_entries=total_entries,
        total_conflicts=len(conflicts),
        conflicts=conflicts,
        mods_analyzed=sorted(mod_entries),
    )
