import logging
from pathlib import Path

import xxhash
from sqlmodel import Session, select

from chat_nexus_mod_manager.matching.grouper import group_mod_files
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModFile, ModGroup
from chat_nexus_mod_manager.schemas.mod import ScanResult

logger = logging.getLogger(__name__)

INTERESTING_EXTENSIONS = {
    ".archive", ".lua", ".dll", ".asi", ".reds", ".yaml", ".yml",
    ".xl", ".json", ".ini", ".toml", ".xml", ".csv",
}

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".vscode"}


def compute_hash(file_path: Path) -> str:
    h = xxhash.xxh64()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_game_mods(game: Game, session: Session) -> ScanResult:
    install_path = Path(game.install_path)
    if not install_path.exists():
        logger.warning("Install path does not exist: %s", install_path)
        return ScanResult(files_found=0, groups_created=0, new_files=0)

    discovered_files: list[ModFile] = []
    new_count = 0

    for mod_path_entry in game.mod_paths:
        full_path = install_path / mod_path_entry.relative_path
        if not full_path.exists():
            logger.debug("Mod path not found: %s", full_path)
            continue

        for file_path in full_path.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            if file_path.suffix.lower() not in INTERESTING_EXTENSIONS:
                # For CET mods, we still want init.lua which has .lua extension
                # For REDmod dirs, there may be .archive files
                # Already covered by extensions set
                continue

            rel = str(file_path.relative_to(install_path))
            existing = session.exec(
                select(ModFile).where(ModFile.file_path == rel)
            ).first()

            if existing:
                discovered_files.append(existing)
                continue

            file_hash = compute_hash(file_path)
            mod_file = ModFile(
                file_path=rel,
                filename=file_path.name,
                file_hash=file_hash,
                file_size=file_path.stat().st_size,
                source_folder=mod_path_entry.relative_path,
            )
            session.add(mod_file)
            discovered_files.append(mod_file)
            new_count += 1

    session.flush()

    ungrouped = [f for f in discovered_files if f.mod_group_id is None]
    groups = group_mod_files(ungrouped)

    groups_created = 0
    for group_name, files, confidence in groups:
        mod_group = ModGroup(
            game_id=game.id,  # type: ignore[arg-type]
            display_name=group_name,
            confidence=confidence,
        )
        session.add(mod_group)
        session.flush()

        for f in files:
            f.mod_group_id = mod_group.id
            session.add(f)
        groups_created += 1

    session.commit()

    try:
        from chat_nexus_mod_manager.vector.indexer import index_mod_groups

        index_mod_groups(game.id)
        logger.info("Auto-indexed mod groups into vector store after scan")
    except Exception:
        logger.warning("Failed to auto-index after scan", exc_info=True)

    return ScanResult(
        files_found=len(discovered_files),
        groups_created=groups_created,
        new_files=new_count,
    )
