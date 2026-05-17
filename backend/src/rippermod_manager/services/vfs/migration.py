"""One-time migration from copy-install (files in game dir) to staged hardlinks."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.constants import CYBERPUNK_DEFAULT_PATHS
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.vfs.naming import unique_staging_name
from rippermod_manager.services.vfs.primitives import hardlink, is_game_running

logger = logging.getLogger(__name__)


@dataclass
class MigrationReport:
    migrated_mods: int = 0
    migrated_files: int = 0
    skipped_files: int = 0
    errors: list[str] = field(default_factory=list)


def migrate_to_vfs(game: Game, session: Session) -> MigrationReport:
    """Move each unmigrated mod's files from the game dir into staging and hardlink back.

    Commits per-mod so that a crash mid-migration leaves the already-migrated mods
    in a consistent state (DB row updated, files in staging, hardlinks in game dir).
    Within a single mod, file moves are reversed on failure.
    """
    if is_game_running():
        return MigrationReport(errors=["Cyberpunk 2077 is running. Close it and retry."])

    install = Path(game.install_path)
    staging_root = install / "downloaded_mods"
    staging_root.mkdir(parents=True, exist_ok=True)

    report = MigrationReport()
    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.staging_dir == "",
        )
    ).all()

    for mod in mods:
        safe = unique_staging_name(staging_root, mod.name)
        staging = staging_root / safe
        _ = mod.files
        ok = True
        moved: list[tuple[Path, Path]] = []
        for f in mod.files:
            game_path = install / f.relative_path.replace("\\", "/")
            staging_path = staging / f.relative_path.replace("\\", "/")
            if not game_path.exists():
                report.skipped_files += 1
                continue
            staging_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(game_path, staging_path)
                hardlink(staging_path, game_path)
                moved.append((staging_path, game_path))
                report.migrated_files += 1
                f.source_path = f.relative_path
                session.add(f)
            except OSError as exc:
                logger.error("migration failed for %s: %s", game_path, exc)
                report.errors.append(f"{game_path}: {exc}")
                ok = False
                # Rollback this mod: restore moved files to game-dir
                for sp, gp in moved:
                    try:
                        if gp.exists():
                            gp.unlink()
                        shutil.move(str(sp), str(gp))
                    except OSError:
                        logger.exception("rollback failed for %s", gp)
                # Discard any uncommitted source_path changes for this mod
                session.rollback()
                break
        if ok:
            mod.staging_dir = safe
            mod.deployed = True
            session.add(mod)
            session.commit()  # commit per mod for crash safety
            report.migrated_mods += 1
    return report


def find_untracked_files(game: Game, session: Session) -> list[str]:
    """Return relative paths under known mod roots that no InstalledModFile claims."""
    install = Path(game.install_path)
    owned: set[str] = set()
    rows = session.exec(
        select(InstalledModFile)
        .join(InstalledMod, InstalledModFile.installed_mod_id == InstalledMod.id)
        .where(InstalledMod.game_id == game.id)
    ).all()
    for row in rows:
        owned.add(row.relative_path.replace("\\", "/").lower())

    untracked: list[str] = []
    for root_rel, _label, _enabled in CYBERPUNK_DEFAULT_PATHS:
        root = install / root_rel
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(install).as_posix().lower()
                if rel not in owned:
                    untracked.append(rel)
    return sorted(untracked)
