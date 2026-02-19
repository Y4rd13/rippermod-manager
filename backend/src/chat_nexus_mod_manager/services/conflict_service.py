"""Conflict detection between mod archives and installed mods.

Checks whether files in a prospective archive already belong to another
installed mod, enabling the user to skip, overwrite, or cancel.
"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from chat_nexus_mod_manager.archive.handler import open_archive
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.schemas.install import ConflictCheckResult, FileConflict
from chat_nexus_mod_manager.services.install_service import get_file_ownership_map


def check_conflicts(
    game: Game,
    archive_path: Path,
    session: Session,
) -> ConflictCheckResult:
    """Scan an archive and report files that conflict with installed mods.

    Returns a ``ConflictCheckResult`` listing every file in the archive
    that is already owned by another installed mod.
    """
    ownership = get_file_ownership_map(session, game.id)  # type: ignore[arg-type]
    conflicts: list[FileConflict] = []
    total_files = 0

    with open_archive(archive_path) as archive:
        for entry in archive.list_entries():
            if entry.is_dir:
                continue
            total_files += 1

            normalised = entry.filename.replace("\\", "/").lower()
            if normalised in ownership:
                mod = ownership[normalised]
                conflicts.append(
                    FileConflict(
                        file_path=entry.filename,
                        owning_mod_id=mod.id,  # type: ignore[arg-type]
                        owning_mod_name=mod.name,
                    )
                )

    return ConflictCheckResult(
        archive_filename=archive_path.name,
        total_files=total_files,
        conflicts=conflicts,
    )
