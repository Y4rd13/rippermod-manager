"""Mod installation, uninstallation, and enable/disable toggle.

Handles archive extraction to the game directory, file ownership tracking
via the InstalledMod/InstalledModFile tables, and non-destructive
enable/disable via ``.disabled`` file renaming.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.archive.handler import ArchiveEntry, open_archive
from rippermod_manager.matching.filename_parser import parse_mod_filename
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.download import DownloadJob
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.nexus.client import NexusClient
from rippermod_manager.schemas.install import (
    ArchiveDeleteResult,
    InstallResult,
    OrphanCleanupResult,
    ToggleResult,
    UninstallResult,
)
from rippermod_manager.services.archive_layout import (
    ArchiveLayout,
    detect_layout,
    known_roots_for_game,
)
from rippermod_manager.services.nexus_helpers import match_local_to_nexus_file

logger = logging.getLogger(__name__)


def list_available_archives(game: Game) -> list[Path]:
    """Return archive files found in a ``staging`` folder next to the game install."""
    staging = Path(game.install_path) / "downloaded_mods"
    if not staging.is_dir():
        return []
    return sorted(
        p for p in staging.iterdir() if p.is_file() and p.suffix.lower() in {".zip", ".7z", ".rar"}
    )


def get_file_ownership_map(session: Session, game_id: int) -> dict[str, InstalledMod]:
    """Build a map of ``{normalised_path: InstalledMod}`` for all installed mods."""
    mods = session.exec(select(InstalledMod).where(InstalledMod.game_id == game_id)).all()
    ownership: dict[str, InstalledMod] = {}
    for mod in mods:
        _ = mod.files
        for f in mod.files:
            ownership[f.relative_path.replace("\\", "/").lower()] = mod
    return ownership


def install_mod(
    game: Game,
    archive_path: Path,
    session: Session,
    skip_conflicts: list[str] | None = None,
    file_renames: dict[str, str] | None = None,
) -> InstallResult:
    """Extract an archive to the game directory and record ownership.

    Returns an ``InstallResult`` with counts of extracted and skipped files.

    Raises:
        FileNotFoundError: If the archive or game directory doesn't exist.
        ValueError: If a mod with the same name is already installed.
    """
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    game_dir = Path(game.install_path)
    if not game_dir.is_dir():
        raise FileNotFoundError(f"Game directory not found: {game_dir}")

    parsed = parse_mod_filename(archive_path.name)

    existing = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.name == parsed.name,
        )
    ).first()
    if existing:
        raise ValueError(f"Mod '{parsed.name}' is already installed. Uninstall first to reinstall.")

    skip_set: set[str] = set()
    if skip_conflicts:
        skip_set = {f.replace("\\", "/").lower() for f in skip_conflicts}

    rename_map: dict[str, str] = {}
    if file_renames:
        rename_map = {k.replace("\\", "/"): v.replace("\\", "/") for k, v in file_renames.items()}

    ownership = get_file_ownership_map(session, game.id)  # type: ignore[arg-type]

    extracted_paths: list[str] = []
    skipped = 0
    overwritten = 0

    with open_archive(archive_path) as archive:
        all_entries = archive.list_entries()

        known_roots = known_roots_for_game(game.domain_name)
        layout_result = detect_layout(all_entries, known_roots)

        if layout_result.layout == ArchiveLayout.FOMOD:
            raise ValueError(
                "FOMOD installer detected. This archive requires a FOMOD-aware "
                "tool (Vortex, MO2) to install."
            )

        strip_prefix = layout_result.strip_prefix

        # Pre-filter entries to determine which files to extract
        valid_entries: list[tuple[ArchiveEntry, str, str]] = []
        for entry in all_entries:
            if entry.is_dir:
                continue
            normalised = entry.filename.replace("\\", "/")

            if strip_prefix:
                if normalised.startswith(strip_prefix + "/"):
                    normalised = normalised[len(strip_prefix) + 1 :]
                else:
                    logger.debug("Skipping entry outside wrapper: %s", entry.filename)
                    skipped += 1
                    continue

            if normalised in rename_map:
                normalised = rename_map[normalised]

            normalised_lower = normalised.lower()
            if normalised_lower in skip_set:
                skipped += 1
                continue
            target = game_dir / normalised
            if not target.resolve().is_relative_to(game_dir.resolve()):
                logger.warning("Skipping path traversal entry: %s", entry.filename)
                skipped += 1
                continue
            valid_entries.append((entry, normalised, normalised_lower))

        # Batch read all valid entries in a single pass (avoids O(N²) for 7z)
        entries_to_read = [e for e, _, _ in valid_entries]
        file_contents = archive.read_all_files(entries_to_read)

        for entry, normalised, normalised_lower in valid_entries:
            data = file_contents.get(entry.filename)
            if data is None:
                logger.warning("Batch read missed entry: %s", entry.filename)
                skipped += 1
                continue
            target = game_dir / normalised
            if target.exists():
                overwritten += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            extracted_paths.append(normalised)

            if normalised_lower in ownership:
                prev_mod = ownership[normalised_lower]
                for f in list(prev_mod.files):
                    if f.relative_path.replace("\\", "/").lower() == normalised_lower:
                        session.delete(f)
                        break

    installed = InstalledMod(
        game_id=game.id,  # type: ignore[arg-type]
        name=parsed.name,
        source_archive=archive_path.name,
        nexus_mod_id=parsed.nexus_mod_id,
        upload_timestamp=parsed.upload_timestamp,
        installed_version=parsed.version or "",
    )
    session.add(installed)
    session.flush()

    # Enrich from download job and correlation data when nexus_mod_id is known
    if parsed.nexus_mod_id:
        job = session.exec(
            select(DownloadJob).where(
                DownloadJob.nexus_mod_id == parsed.nexus_mod_id,
                DownloadJob.status == "completed",
                DownloadJob.file_name == archive_path.name,
            )
        ).first()
        if job:
            installed.nexus_file_id = job.nexus_file_id

        # Fallback: check NexusDownload for a previously resolved file_id
        if not installed.nexus_file_id:
            nx_dl = session.exec(
                select(NexusDownload).where(
                    NexusDownload.game_id == game.id,
                    NexusDownload.nexus_mod_id == parsed.nexus_mod_id,
                    NexusDownload.file_id.is_not(None),  # type: ignore[union-attr]
                )
            ).first()
            if nx_dl and nx_dl.file_id:
                installed.nexus_file_id = nx_dl.file_id

        corr = session.exec(
            select(ModNexusCorrelation)
            .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
            .where(NexusDownload.nexus_mod_id == parsed.nexus_mod_id)
            .order_by(ModNexusCorrelation.score.desc())  # type: ignore[union-attr]
        ).first()
        if corr:
            installed.mod_group_id = corr.mod_group_id

    for rel_path in extracted_paths:
        session.add(
            InstalledModFile(
                installed_mod_id=installed.id,  # type: ignore[arg-type]
                relative_path=rel_path,
            )
        )

    session.commit()
    session.refresh(installed)

    # Index .archive files for resource-level conflict detection
    from rippermod_manager.services.archive_index_service import index_mod_archives

    _ = installed.files  # ensure files are loaded
    index_mod_archives(game, installed, session)
    session.commit()

    logger.info(
        "Installed '%s' (%d files, %d overwritten)", parsed.name, len(extracted_paths), overwritten
    )
    return InstallResult(
        installed_mod_id=installed.id,  # type: ignore[arg-type]
        name=parsed.name,
        files_extracted=len(extracted_paths),
        files_skipped=skipped,
        files_overwritten=overwritten,
    )


def uninstall_mod(
    installed_mod: InstalledMod,
    game: Game,
    session: Session,
) -> UninstallResult:
    """Delete all files owned by a mod and remove the DB record."""
    game_dir = Path(game.install_path)
    deleted = 0
    dirs_removed = 0

    _ = installed_mod.files
    for f in installed_mod.files:
        file_path = game_dir / f.relative_path.replace("/", os.sep)
        if file_path.exists():
            try:
                file_path.unlink()
                deleted += 1
                parent = file_path.parent
                while parent != game_dir:
                    if not any(parent.iterdir()):
                        parent.rmdir()
                        dirs_removed += 1
                        parent = parent.parent
                    else:
                        break
            except OSError:
                logger.warning("Could not delete %s", file_path)
        else:
            disabled_path = file_path.with_suffix(file_path.suffix + ".disabled")
            if disabled_path.exists():
                try:
                    disabled_path.unlink()
                    deleted += 1
                except OSError:
                    logger.warning("Could not delete %s", disabled_path)

    # Clean up archive entry index before deleting the mod record
    from rippermod_manager.services.archive_index_service import remove_index_for_mod

    remove_index_for_mod(session, installed_mod.id)  # type: ignore[arg-type]

    session.delete(installed_mod)
    session.commit()

    logger.info("Uninstalled '%s' (%d files deleted)", installed_mod.name, deleted)
    return UninstallResult(files_deleted=deleted, directories_removed=dirs_removed)


def toggle_mod(
    installed_mod: InstalledMod,
    game: Game,
    session: Session,
    *,
    commit: bool = True,
) -> ToggleResult:
    """Enable or disable a mod by renaming its files with ``.disabled`` suffix.

    Pass ``commit=False`` to defer the DB commit (useful for batching in
    profile loads).
    """
    game_dir = Path(game.install_path)
    should_disable = not installed_mod.disabled
    affected = 0

    _ = installed_mod.files
    for f in installed_mod.files:
        file_path = game_dir / f.relative_path.replace("/", os.sep)

        if should_disable:
            if file_path.exists():
                disabled_path = file_path.with_suffix(file_path.suffix + ".disabled")
                try:
                    file_path.rename(disabled_path)
                    affected += 1
                except OSError:
                    logger.warning("Could not disable %s", file_path)
        else:
            disabled_path = file_path.with_suffix(file_path.suffix + ".disabled")
            if disabled_path.exists():
                try:
                    disabled_path.rename(file_path)
                    affected += 1
                except OSError:
                    logger.warning("Could not enable %s", disabled_path)

    installed_mod.disabled = should_disable
    session.add(installed_mod)
    if commit:
        session.commit()

    action = "Disabled" if should_disable else "Enabled"
    logger.info("%s '%s' (%d files)", action, installed_mod.name, affected)
    return ToggleResult(disabled=should_disable, files_affected=affected)


async def resolve_installed_file_id(
    installed_mod_id: int,
    game_domain: str,
    nexus_mod_id: int,
    source_archive: str,
    api_key: str,
) -> None:
    """Best-effort background resolution of nexus_file_id for an installed mod.

    Creates its own DB session so it can run independently of the request lifecycle.
    """
    import asyncio

    from rippermod_manager.database import engine

    try:
        async with NexusClient(api_key) as client:
            files_resp = await client.get_mod_files(
                game_domain,
                nexus_mod_id,
                category="main,update,optional,miscellaneous",
            )
    except Exception:
        logger.debug("Could not fetch files for mod %d", nexus_mod_id)
        return

    nexus_files = files_resp.get("files", [])
    if not nexus_files:
        return

    parsed = parse_mod_filename(source_archive)
    matched = match_local_to_nexus_file(
        source_archive,
        nexus_files,
        parsed_version=parsed.version,
        parsed_timestamp=parsed.upload_timestamp,
        strict=True,
    )
    if not matched:
        return

    def _persist() -> None:
        with Session(engine) as session:
            installed = session.get(InstalledMod, installed_mod_id)
            if not installed or installed.nexus_file_id:
                return
            installed.nexus_file_id = matched.get("file_id")
            if matched.get("uploaded_timestamp") and not installed.upload_timestamp:
                installed.upload_timestamp = matched["uploaded_timestamp"]
            session.add(installed)
            session.commit()

    await asyncio.to_thread(_persist)


def delete_archive(game_path: str, filename: str) -> ArchiveDeleteResult:
    """Delete a single archive file from the staging folder.

    Validates the filename to prevent path traversal attacks.
    """
    staging = Path(game_path) / "downloaded_mods"
    archive_path = staging / filename
    if not archive_path.resolve().is_relative_to(staging.resolve()):
        return ArchiveDeleteResult(filename=filename, deleted=False, message="Invalid filename")

    if not archive_path.exists():
        return ArchiveDeleteResult(filename=filename, deleted=False, message="File not found")

    try:
        archive_path.unlink()
    except OSError as exc:
        logger.warning("Failed to delete archive %s: %s", archive_path, exc)
        return ArchiveDeleteResult(filename=filename, deleted=False, message=str(exc))

    logger.info("Deleted archive: %s", filename)
    return ArchiveDeleteResult(filename=filename, deleted=True, message="Deleted")


def find_orphaned_archives(
    game: Game,
    session: Session,
) -> list[str]:
    """Return archive filenames not referenced by any installed mod or active download."""
    staging = Path(game.install_path) / "downloaded_mods"
    if not staging.is_dir():
        return []

    all_files = {
        p.name
        for p in staging.iterdir()
        if p.is_file() and p.suffix.lower() in {".zip", ".7z", ".rar"}
    }
    if not all_files:
        return []

    installed_archives: set[str] = set()
    installed_mods = session.exec(
        select(InstalledMod.source_archive).where(
            InstalledMod.game_id == game.id,
            InstalledMod.source_archive != "",
        )
    ).all()
    for sa in installed_mods:
        installed_archives.add(sa)

    active_downloads: set[str] = set()
    active_jobs = session.exec(
        select(DownloadJob.file_name).where(
            DownloadJob.game_id == game.id,
            DownloadJob.status.in_(["pending", "downloading", "completed"]),
            DownloadJob.file_name != "",
        )
    ).all()
    for fn in active_jobs:
        active_downloads.add(fn)

    referenced = installed_archives | active_downloads
    return sorted(all_files - referenced)


def delete_orphaned_archives(
    game: Game,
    session: Session,
) -> OrphanCleanupResult:
    """Delete all orphaned archives and return a summary."""
    orphans = find_orphaned_archives(game, session)
    staging = Path(game.install_path) / "downloaded_mods"

    deleted_files: list[str] = []
    freed_bytes = 0

    for filename in orphans:
        archive_path = staging / filename
        try:
            size = archive_path.stat().st_size
            archive_path.unlink()
            freed_bytes += size
            deleted_files.append(filename)
        except OSError as exc:
            logger.warning("Failed to delete orphan %s: %s", filename, exc)

    if deleted_files:
        logger.info("Cleaned %d orphan archives, freed %d bytes", len(deleted_files), freed_bytes)

    return OrphanCleanupResult(
        deleted_count=len(deleted_files),
        freed_bytes=freed_bytes,
        deleted_files=deleted_files,
    )
