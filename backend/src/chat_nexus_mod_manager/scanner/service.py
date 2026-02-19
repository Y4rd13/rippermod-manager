import logging
from collections.abc import Callable
from pathlib import Path

import xxhash
from sqlmodel import Session, select

from chat_nexus_mod_manager.matching.grouper import group_mod_files
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModFile, ModGroup
from chat_nexus_mod_manager.schemas.mod import ScanResult

logger = logging.getLogger(__name__)

INTERESTING_EXTENSIONS = {
    ".archive",
    ".lua",
    ".dll",
    ".asi",
    ".reds",
    ".yaml",
    ".yml",
    ".xl",
    ".json",
    ".ini",
    ".toml",
    ".xml",
    ".csv",
}

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".vscode"}

ProgressCallback = Callable[[str, str, int], None]


def _noop_progress(_phase: str, _msg: str, _pct: int) -> None:
    pass


def compute_hash(file_path: Path) -> str:
    h = xxhash.xxh64()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _discover_files(game: Game) -> list[tuple[Path, str]]:
    install_path = Path(game.install_path)
    files: list[tuple[Path, str]] = []
    for mod_path_entry in game.mod_paths:
        full_path = install_path / mod_path_entry.relative_path
        if not full_path.exists():
            continue
        for file_path in full_path.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            if file_path.suffix.lower() in INTERESTING_EXTENSIONS:
                files.append((file_path, mod_path_entry.relative_path))
    return files


def scan_game_mods(
    game: Game,
    session: Session,
    on_progress: ProgressCallback = _noop_progress,
) -> ScanResult:
    install_path = Path(game.install_path)
    if not install_path.exists():
        logger.warning("Install path does not exist: %s", install_path)
        on_progress("error", f"Install path not found: {install_path}", 0)
        return ScanResult(files_found=0, groups_created=0, new_files=0)

    on_progress("scan", "Discovering mod files...", 0)
    candidate_files = _discover_files(game)
    total_files = len(candidate_files)
    on_progress("scan", f"Found {total_files} candidate files", 0)

    if total_files == 0:
        on_progress("done", "No mod files found", 100)
        return ScanResult(files_found=0, groups_created=0, new_files=0)

    discovered_files: list[ModFile] = []
    new_count = 0

    for i, (file_path, source_folder) in enumerate(candidate_files):
        pct = int(((i + 1) / total_files) * 70)

        rel = str(file_path.relative_to(install_path))
        existing = session.exec(select(ModFile).where(ModFile.file_path == rel)).first()

        if existing:
            discovered_files.append(existing)
            on_progress("scan", f"Known: {file_path.name}", pct)
            continue

        file_hash = compute_hash(file_path)
        mod_file = ModFile(
            file_path=rel,
            filename=file_path.name,
            file_hash=file_hash,
            file_size=file_path.stat().st_size,
            source_folder=source_folder,
        )
        session.add(mod_file)
        discovered_files.append(mod_file)
        new_count += 1
        on_progress("scan", f"New: {file_path.name}", pct)

    session.flush()
    on_progress("group", "Grouping mod files...", 75)

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
        on_progress("group", f"Created group: {group_name}", -1)

    session.commit()
    on_progress("index", "Indexing into vector store...", 78)

    try:
        from chat_nexus_mod_manager.vector.indexer import index_mod_groups

        index_mod_groups(game.id)
        on_progress("index", "Vector index updated", 83)
    except ImportError:
        on_progress("index", "Vector indexing skipped (not configured)", 83)
        logger.info("ChromaDB not available, skipping vector indexing")
    except Exception:
        on_progress("index", "Vector indexing failed", 83)
        logger.warning("Failed to auto-index after scan", exc_info=True)

    msg = f"Scan complete: {len(discovered_files)} files, {groups_created} groups"
    on_progress("index", msg, 85)

    return ScanResult(
        files_found=len(discovered_files),
        groups_created=groups_created,
        new_files=new_count,
    )
