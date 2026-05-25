"""Orchestrates 'adopt in place' migration of existing on-disk mods.

Gates on the game not running, takes a save backup, then adopts each group
via ``install_service.adopt_mod`` with per-mod isolation: one group's failure
is recorded and the loop continues. Optionally streams progress.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlmodel import Session

from rippermod_manager.models.game import Game
from rippermod_manager.services.install_service import adopt_mod
from rippermod_manager.services.progress import ProgressCallback, noop_progress
from rippermod_manager.services.save_backup_service import maybe_backup_before
from rippermod_manager.services.vfs.primitives import is_game_running

logger = logging.getLogger(__name__)

GAME_EXE = "Cyberpunk2077.exe"


@dataclass
class AdoptReport:
    adopted_mods: int = 0
    adopted_files: int = 0
    skipped_files: int = 0
    game_running: bool = False
    errors: list[str] = field(default_factory=list)


def adopt_detected(
    game: Game,
    groups: list[dict],
    session: Session,
    *,
    on_progress: ProgressCallback = noop_progress,
) -> AdoptReport:
    """Adopt the given groups. Each group dict: {name, relative_paths[], nexus_mod_id?}.

    Refuses (no-op) if the game is running. Takes a single ``pre-migration`` save
    backup before any move. Adopts groups one at a time; a per-group failure is
    rolled back inside ``adopt_mod`` and recorded in ``errors`` without aborting
    the rest.
    """
    report = AdoptReport()
    if is_game_running(GAME_EXE):
        report.game_running = True
        report.errors.append("Cyberpunk 2077 is running. Close it and retry.")
        return report

    maybe_backup_before(game, session, reason="pre-migration")

    total = len(groups)
    for i, group in enumerate(groups):
        name = group["name"]
        rel_paths = group["relative_paths"]
        nexus_mod_id = group.get("nexus_mod_id")
        on_progress("adopt", f"Adopting {name}", int((i / total) * 100) if total else 0)
        try:
            result = adopt_mod(game, name, rel_paths, session, nexus_mod_id=nexus_mod_id)
            report.adopted_mods += 1
            report.adopted_files += result.files_extracted
            report.skipped_files += result.files_skipped
        except (ValueError, OSError) as exc:
            logger.error("adopt_detected: group '%s' failed: %s", name, exc)
            report.errors.append(f"{name}: {exc}")
            session.rollback()

    on_progress("done", f"Adopted {report.adopted_mods} mods", 100)
    return report
