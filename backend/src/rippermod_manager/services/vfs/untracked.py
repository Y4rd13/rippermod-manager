"""Find files in the game dir not owned by any installed mod."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.constants import CYBERPUNK_DEFAULT_PATHS, is_vanilla_path
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile


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
                if rel in owned or is_vanilla_path(rel):
                    continue
                untracked.append(rel)
    return sorted(untracked)
