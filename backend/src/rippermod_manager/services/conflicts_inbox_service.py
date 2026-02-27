"""Conflicts inbox service — detects cross-mod file conflicts post-install.

Builds a global view of which installed mods have lost files to later
installations, enabling users to see the conflict landscape and resolve
conflicts by reinstalling mods.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.archive.handler import open_archive
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.schemas.conflicts import (
    ConflictEvidence,
    ConflictsOverview,
    InboxSeverity,
    ModConflictDetail,
    ModConflictSummary,
    ResolveResult,
)
from rippermod_manager.services.archive_layout import detect_layout, known_roots_for_game
from rippermod_manager.services.install_service import (
    get_file_ownership_map,
    install_mod,
    uninstall_mod,
)

logger = logging.getLogger(__name__)


def _compute_severity(conflict_count: int, total_files: int) -> InboxSeverity:
    if total_files == 0 or conflict_count == 0:
        return InboxSeverity.info
    ratio = conflict_count / total_files
    if ratio > 0.5:
        return InboxSeverity.critical
    return InboxSeverity.warning


def _archive_files_for_mod(
    mod: InstalledMod,
    game: Game,
) -> list[str] | None:
    """Return normalised file paths from the mod's source archive, or None if unavailable."""
    if not mod.source_archive:
        return None

    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / mod.source_archive
    if not archive_path.is_file():
        return None

    if archive_path.stat().st_size == 0:
        return None

    try:
        with open_archive(archive_path) as archive:
            all_entries = archive.list_entries()
    except Exception:
        logger.warning("Could not open archive %s — skipping conflict check", archive_path)
        return None

    known_roots = known_roots_for_game(game.domain_name)
    layout_result = detect_layout(all_entries, known_roots)
    strip_prefix = layout_result.strip_prefix

    files: list[str] = []
    for entry in all_entries:
        if entry.is_dir:
            continue
        normalised = entry.filename.replace("\\", "/")
        if strip_prefix and normalised.startswith(strip_prefix + "/"):
            normalised = normalised[len(strip_prefix) + 1 :]
        files.append(normalised)
    return files


def get_conflicts_overview(game: Game, session: Session) -> ConflictsOverview:
    """Build a summary of all file conflicts across installed mods."""
    ownership = get_file_ownership_map(session, game.id)  # type: ignore[arg-type]

    mods = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()

    summaries: list[ModConflictSummary] = []

    for mod in mods:
        archive_files = _archive_files_for_mod(mod, game)
        if archive_files is None:
            continue

        evidence: list[tuple[str, InstalledMod]] = []
        for file_path in archive_files:
            normalised_lower = file_path.replace("\\", "/").lower()
            owner = ownership.get(normalised_lower)
            if owner and owner.id != mod.id:
                evidence.append((file_path, owner))

        if not evidence:
            continue

        conflict_count = len(evidence)
        severity = _compute_severity(conflict_count, len(archive_files))
        conflicting_names = sorted({owner.name for _, owner in evidence})

        summaries.append(
            ModConflictSummary(
                mod_id=mod.id,  # type: ignore[arg-type]
                mod_name=mod.name,
                source_archive=mod.source_archive,
                total_archive_files=len(archive_files),
                conflict_count=conflict_count,
                severity=severity,
                conflicting_mod_names=conflicting_names,
            )
        )

    total_conflicts = sum(s.conflict_count for s in summaries)
    return ConflictsOverview(
        total_conflicts=total_conflicts,
        mods_affected=len(summaries),
        summaries=summaries,
    )


def get_mod_conflict_detail(
    game: Game,
    mod: InstalledMod,
    session: Session,
) -> ModConflictDetail:
    """Build detailed file-level conflict evidence for a single mod."""
    ownership = get_file_ownership_map(session, game.id)  # type: ignore[arg-type]
    archive_files = _archive_files_for_mod(mod, game)

    evidence: list[ConflictEvidence] = []
    if archive_files:
        for file_path in archive_files:
            normalised_lower = file_path.replace("\\", "/").lower()
            owner = ownership.get(normalised_lower)
            if owner and owner.id != mod.id:
                evidence.append(
                    ConflictEvidence(
                        file_path=file_path,
                        winner_mod_id=owner.id,  # type: ignore[arg-type]
                        winner_mod_name=owner.name,
                    )
                )

    return ModConflictDetail(
        mod_id=mod.id,  # type: ignore[arg-type]
        mod_name=mod.name,
        source_archive=mod.source_archive,
        total_archive_files=len(archive_files) if archive_files else 0,
        evidence=evidence,
    )


def resolve_conflict(
    game: Game,
    mod: InstalledMod,
    session: Session,
    *,
    action: str = "reinstall",
) -> ResolveResult:
    """Resolve conflicts by the given action (currently only 'reinstall')."""
    if not mod.source_archive:
        raise ValueError("Mod has no source archive — cannot reinstall.")

    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / mod.source_archive
    if not archive_path.is_file():
        raise FileNotFoundError(f"Source archive not found: {mod.source_archive}")

    # Count current conflicts before reinstall
    ownership = get_file_ownership_map(session, game.id)  # type: ignore[arg-type]
    archive_files = _archive_files_for_mod(mod, game) or []
    pre_conflicts = 0
    for file_path in archive_files:
        normalised_lower = file_path.replace("\\", "/").lower()
        owner = ownership.get(normalised_lower)
        if owner and owner.id != mod.id:
            pre_conflicts += 1

    # Uninstall then reinstall
    uninstall_mod(mod, game, session)
    try:
        result = install_mod(game, archive_path, session)
    except Exception:
        logger.error(
            "Reinstall failed after uninstall for mod %s — mod is now uninstalled",
            mod.name,
        )
        raise

    return ResolveResult(
        installed_mod_id=result.installed_mod_id,
        files_extracted=result.files_extracted,
        files_reclaimed=pre_conflicts,
    )
