"""Archive entry indexer — parses RDAR TOCs and persists hash entries.

Enumerates .archive files from game mod paths, parses each file's TOC,
and stores the resource hashes in the archive_entry_index table for
fast conflict detection.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.archive.rdar_parser import parse_rdar_toc
from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)


def _discover_archive_files(game: Game) -> list[tuple[Path, str]]:
    """Find all .archive files in the game's mod paths.

    Returns (absolute_path, relative_path_from_install_dir) tuples.
    """
    install_path = Path(game.install_path)
    archives: list[tuple[Path, str]] = []
    for mod_path_entry in game.mod_paths:
        full_path = install_path / mod_path_entry.relative_path
        if not full_path.exists():
            continue
        for file_path in full_path.rglob("*.archive"):
            if not file_path.is_file():
                continue
            rel = str(file_path.relative_to(install_path)).replace("\\", "/")
            archives.append((file_path, rel))
    return archives


def _build_file_to_mod_map(session: Session, game_id: int) -> dict[str, int]:
    """Map normalised relative_path -> installed_mod_id for .archive files."""
    stmt = (
        select(InstalledModFile.relative_path, InstalledModFile.installed_mod_id)
        .join(InstalledMod, InstalledModFile.installed_mod_id == InstalledMod.id)
        .where(InstalledMod.game_id == game_id)
    )
    rows = session.exec(stmt).all()
    result: dict[str, int] = {}
    for rel_path, mod_id in rows:
        normalised = rel_path.replace("\\", "/").lower()
        if normalised.endswith(".archive"):
            result[normalised] = mod_id
    return result


def index_game_archives(
    game: Game,
    session: Session,
    *,
    force_reindex: bool = False,
    on_progress: ProgressCallback = noop_progress,
) -> int:
    """Index all .archive files for a game.

    Returns the number of newly indexed entries.  If *force_reindex* is
    ``False`` (default), skips archives whose relative path is already
    present in the index for this game.
    """
    game_id: int = game.id  # type: ignore[assignment]

    already_indexed: set[str] = set()
    if not force_reindex:
        rows = session.exec(
            select(ArchiveEntryIndex.archive_relative_path).where(
                ArchiveEntryIndex.game_id == game_id
            )
        ).all()
        already_indexed = set(rows)
    else:
        existing = session.exec(
            select(ArchiveEntryIndex).where(ArchiveEntryIndex.game_id == game_id)
        ).all()
        for row in existing:
            session.delete(row)
        session.flush()

    on_progress("archive-index", "Discovering .archive files...", 0)
    archive_files = _discover_archive_files(game)
    total = len(archive_files)
    if total == 0:
        on_progress("archive-index", "No .archive files found", 100)
        return 0

    file_to_mod = _build_file_to_mod_map(session, game_id)

    new_entries = 0
    for i, (abs_path, rel_path) in enumerate(archive_files):
        pct = int(((i + 1) / total) * 100)
        filename = abs_path.name

        if rel_path in already_indexed:
            on_progress("archive-index", f"Skipped (cached): {filename}", pct)
            continue

        try:
            toc = parse_rdar_toc(abs_path)
        except (ValueError, OSError) as exc:
            logger.warning("Failed to parse %s: %s", abs_path, exc)
            on_progress("archive-index", f"Failed: {filename}", pct)
            continue

        normalised_rel = rel_path.replace("\\", "/").lower()
        mod_id = file_to_mod.get(normalised_rel)

        for entry in toc.hash_entries:
            session.add(
                ArchiveEntryIndex(
                    game_id=game_id,
                    installed_mod_id=mod_id,
                    archive_filename=filename,
                    archive_relative_path=rel_path,
                    resource_hash=entry.hash,
                    sha1_hex=entry.sha1.hex(),
                )
            )
            new_entries += 1

        on_progress(
            "archive-index",
            f"Indexed: {filename} ({len(toc.hash_entries)} entries)",
            pct,
        )

    session.commit()
    on_progress("archive-index", f"Indexed {new_entries} entries from {total} archives", 100)
    logger.info("Indexed %d archive entries for game_id=%d", new_entries, game_id)
    return new_entries


def remove_index_for_mod(session: Session, installed_mod_id: int) -> int:
    """Remove index entries for a specific installed mod (called on uninstall)."""
    rows = session.exec(
        select(ArchiveEntryIndex).where(ArchiveEntryIndex.installed_mod_id == installed_mod_id)
    ).all()
    count = len(rows)
    for row in rows:
        session.delete(row)
    return count
