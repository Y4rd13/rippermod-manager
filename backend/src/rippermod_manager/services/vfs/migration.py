"""One-time migration from copy-install (files in game dir) to staged hardlinks."""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.services.vfs.primitives import hardlink, is_game_running

logger = logging.getLogger(__name__)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "mod"


@dataclass
class MigrationReport:
    migrated_mods: int = 0
    migrated_files: int = 0
    skipped_files: int = 0
    errors: list[str] = field(default_factory=list)


def migrate_to_vfs(game: Game, session: Session) -> MigrationReport:
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
        safe = _safe(mod.name)
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
                break
        if ok:
            mod.staging_dir = safe
            mod.deployed = True
            session.add(mod)
            report.migrated_mods += 1
    session.commit()
    return report
