"""Conflict detection between mod archives and installed mods.

Checks whether files in a prospective archive already belong to another
installed mod, enabling the user to skip, overwrite, or cancel.
Also provides installed-vs-installed conflict detection across all mods.
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.archive.handler import open_archive
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.schemas.conflicts import (
    ConflictSeverity,
    InstalledConflictsResult,
    ModConflictPair,
    PairwiseConflictResult,
    SkippedMod,
)
from rippermod_manager.schemas.install import ConflictCheckResult, FileConflict
from rippermod_manager.services.archive_layout import (
    ArchiveLayout,
    detect_layout,
    known_roots_for_game,
)
from rippermod_manager.services.install_service import get_file_ownership_map

logger = logging.getLogger(__name__)


def check_conflicts(
    game: Game,
    archive_path: Path,
    session: Session,
) -> ConflictCheckResult:
    """Scan an archive and report files that conflict with installed mods.

    Returns a ``ConflictCheckResult`` listing every file in the archive
    that is already owned by another installed mod.
    """
    with open_archive(archive_path) as archive:
        all_entries = archive.list_entries()

    known_roots = known_roots_for_game(game.domain_name)
    layout_result = detect_layout(all_entries, known_roots)

    if layout_result.layout == ArchiveLayout.FOMOD:
        return ConflictCheckResult(
            archive_filename=archive_path.name,
            total_files=0,
            conflicts=[],
            is_fomod=True,
        )

    strip_prefix = layout_result.strip_prefix
    ownership = get_file_ownership_map(session, game.id)  # type: ignore[arg-type]
    conflicts: list[FileConflict] = []
    total_files = 0

    for entry in all_entries:
        if entry.is_dir:
            continue
        total_files += 1

        normalised = entry.filename.replace("\\", "/")
        if strip_prefix and normalised.startswith(strip_prefix + "/"):
            normalised = normalised[len(strip_prefix) + 1 :]
        normalised_lower = normalised.lower()

        if normalised_lower in ownership:
            mod = ownership[normalised_lower]
            conflicts.append(
                FileConflict(
                    file_path=normalised,
                    owning_mod_id=mod.id,  # type: ignore[arg-type]
                    owning_mod_name=mod.name,
                )
            )

    return ConflictCheckResult(
        archive_filename=archive_path.name,
        total_files=total_files,
        conflicts=conflicts,
    )


# ---------------------------------------------------------------------------
# Installed-vs-installed conflict detection
# ---------------------------------------------------------------------------


def _severity_for_count(count: int) -> ConflictSeverity:
    """Map a conflicting-file count to a severity level."""
    if count >= 10:
        return ConflictSeverity.HIGH
    if count >= 3:
        return ConflictSeverity.MEDIUM
    return ConflictSeverity.LOW


def _get_archive_file_set(game: Game, archive_filename: str) -> set[str] | None:
    """Open an installed mod's source archive and return its normalised file paths.

    Returns ``None`` when the archive is missing, corrupt, or is a FOMOD
    installer (conditional file sets cannot be reliably compared).
    """
    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / archive_filename
    if not archive_path.is_file():
        return None

    try:
        with open_archive(archive_path) as archive:
            all_entries = archive.list_entries()
    except Exception:
        logger.debug("Failed to open archive %s", archive_path, exc_info=True)
        return None

    known_roots = known_roots_for_game(game.domain_name)
    layout_result = detect_layout(all_entries, known_roots)

    if layout_result.layout == ArchiveLayout.FOMOD:
        return None

    strip_prefix = layout_result.strip_prefix
    file_set: set[str] = set()
    for entry in all_entries:
        if entry.is_dir:
            continue
        normalised = entry.filename.replace("\\", "/")
        if strip_prefix and normalised.startswith(strip_prefix + "/"):
            normalised = normalised[len(strip_prefix) + 1 :]
        file_set.add(normalised.lower())
    return file_set


def check_installed_conflicts(
    game: Game,
    session: Session,
    severity_filter: ConflictSeverity | None = None,
) -> InstalledConflictsResult:
    """Compare all installed mods pairwise to find file conflicts.

    Re-reads source archives from ``downloaded_mods/`` because
    ``install_mod()`` deletes the loser's ``InstalledModFile`` records on
    overwrite.  Mods whose archives are missing or unreadable are reported
    in ``skipped_mods``.
    """
    mods = session.exec(
        select(InstalledMod).where(InstalledMod.game_id == game.id)  # type: ignore[arg-type]
    ).all()

    # Build file sets, collecting skipped mods
    file_sets: dict[int, set[str]] = {}
    skipped: list[SkippedMod] = []
    for mod in mods:
        mod_id: int = mod.id  # type: ignore[assignment]
        if not mod.source_archive:
            skipped.append(
                SkippedMod(
                    mod_id=mod_id,
                    mod_name=mod.name,
                    reason="no source archive",
                )
            )
            continue
        fs = _get_archive_file_set(game, mod.source_archive)
        if fs is None:
            skipped.append(
                SkippedMod(
                    mod_id=mod_id,
                    mod_name=mod.name,
                    reason="archive missing or unreadable",
                )
            )
            continue
        file_sets[mod_id] = fs

    # Map mod id -> InstalledMod for quick lookup
    mod_by_id: dict[int, InstalledMod] = {m.id: m for m in mods}  # type: ignore[misc]

    conflict_pairs: list[ModConflictPair] = []
    for (id_a, files_a), (id_b, files_b) in itertools.combinations(file_sets.items(), 2):
        overlap = sorted(files_a & files_b)
        if not overlap:
            continue
        sev = _severity_for_count(len(overlap))
        if severity_filter and sev != severity_filter:
            continue
        mod_a = mod_by_id[id_a]
        mod_b = mod_by_id[id_b]
        # Winner is the mod installed later (it overwrote the earlier one)
        winner = mod_a.name if mod_a.installed_at >= mod_b.installed_at else mod_b.name
        conflict_pairs.append(
            ModConflictPair(
                mod_a_id=id_a,
                mod_a_name=mod_a.name,
                mod_b_id=id_b,
                mod_b_name=mod_b.name,
                conflicting_files=overlap,
                severity=sev,
                winner=winner,
            )
        )

    return InstalledConflictsResult(
        game_name=game.name,
        total_mods_checked=len(file_sets),
        conflict_pairs=conflict_pairs,
        skipped_mods=skipped,
    )


def check_pairwise_conflict(
    game: Game,
    mod_a: InstalledMod,
    mod_b: InstalledMod,
) -> PairwiseConflictResult:
    """Compare two specific installed mods for file conflicts."""
    mod_a_id: int = mod_a.id  # type: ignore[assignment]
    mod_b_id: int = mod_b.id  # type: ignore[assignment]

    files_a = _get_archive_file_set(game, mod_a.source_archive) if mod_a.source_archive else None
    files_b = _get_archive_file_set(game, mod_b.source_archive) if mod_b.source_archive else None

    if files_a is None or files_b is None:
        missing = []
        if files_a is None:
            missing.append(mod_a.name)
        if files_b is None:
            missing.append(mod_b.name)
        return PairwiseConflictResult(
            mod_a_id=mod_a_id,
            mod_a_name=mod_a.name,
            mod_b_id=mod_b_id,
            mod_b_name=mod_b.name,
            conflicting_files=[],
            severity=None,
            winner=None,
        )

    overlap = sorted(files_a & files_b)
    if not overlap:
        return PairwiseConflictResult(
            mod_a_id=mod_a_id,
            mod_a_name=mod_a.name,
            mod_b_id=mod_b_id,
            mod_b_name=mod_b.name,
            conflicting_files=[],
            severity=None,
            winner=None,
        )

    winner = mod_a.name if mod_a.installed_at >= mod_b.installed_at else mod_b.name
    return PairwiseConflictResult(
        mod_a_id=mod_a_id,
        mod_a_name=mod_a.name,
        mod_b_id=mod_b_id,
        mod_b_name=mod_b.name,
        conflicting_files=overlap,
        severity=_severity_for_count(len(overlap)),
        winner=winner,
    )
