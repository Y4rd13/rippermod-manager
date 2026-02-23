"""Conflict detection between mod archives and installed mods.

Checks whether files in a prospective archive already belong to another
installed mod, enabling the user to skip, overwrite, or cancel.
"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from rippermod_manager.archive.handler import open_archive
from rippermod_manager.models.game import Game
from rippermod_manager.schemas.install import ConflictCheckResult, FileConflict
from rippermod_manager.services.archive_layout import (
    ArchiveLayout,
    detect_layout,
    known_roots_for_game,
)
from rippermod_manager.services.install_service import get_file_ownership_map


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
