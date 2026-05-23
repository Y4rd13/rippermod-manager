"""Mod installation, uninstallation, and enable/disable toggle.

Handles archive extraction to a per-mod staging directory under
``<game>/downloaded_mods/<safe_name>/``, then deploys via hardlinks into
the canonical game-directory paths (VFS model).  Enable/disable and
uninstall operate on the hardlinks; the staging copy is the authoritative
source.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import httpx
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
    apply_layout_transform,
    detect_layout,
    known_roots_for_game,
)
from rippermod_manager.services.nexus_helpers import match_local_to_nexus_file
from rippermod_manager.services.paths import get_mods_dir
from rippermod_manager.services.vfs.naming import unique_staging_name

logger = logging.getLogger(__name__)


def list_available_archives(game: Game) -> list[Path]:
    """Return archive files found in a ``staging`` folder next to the game install."""
    staging = get_mods_dir(game)
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
    auto_deploy: bool = True,
) -> InstallResult:
    """Extract an archive to staging and deploy via hardlinks into the game directory.

    Files are written to ``<game>/downloaded_mods/<safe_name>/...`` first, then
    ``deploy_service.deploy()`` creates hardlinks at the canonical game-dir paths.
    After a successful install the game-dir paths exist (as hardlinks) and behave
    identically to regular files.

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

    staging_parent = get_mods_dir(game)
    staging_parent.mkdir(parents=True, exist_ok=True)
    safe_name = unique_staging_name(staging_parent, parsed.name)
    staging_root = staging_parent / safe_name
    staging_root.mkdir(parents=True, exist_ok=True)

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

        # Pre-filter entries to determine which files to extract
        valid_entries: list[tuple[ArchiveEntry, str, str]] = []
        for entry in all_entries:
            if entry.is_dir:
                continue

            transformed = apply_layout_transform(entry.filename, layout_result)
            if transformed is None:
                logger.debug("Skipping entry outside wrapper: %s", entry.filename)
                skipped += 1
                continue
            normalised = transformed

            if normalised in rename_map:
                normalised = rename_map[normalised]

            normalised_lower = normalised.lower()
            if normalised_lower in skip_set:
                skipped += 1
                continue
            # Path traversal guard: ensure target stays under staging_root
            staging_target = staging_root / normalised
            try:
                staging_target.resolve().relative_to(staging_root.resolve())
            except ValueError:
                logger.warning("Skipping path traversal entry: %s", entry.filename)
                skipped += 1
                continue
            valid_entries.append((entry, normalised, normalised_lower))

        # Batch read all valid entries in a single pass (avoids O(N²) for 7z)
        entries_to_read = [e for e, _, _ in valid_entries]
        file_contents = archive.read_all_files(entries_to_read)

        for entry, normalised, _normalised_lower in valid_entries:
            data = file_contents.get(entry.filename)
            if data is None:
                logger.warning("Batch read missed entry: %s", entry.filename)
                skipped += 1
                continue
            staging_target = staging_root / normalised
            if staging_target.exists():
                overwritten += 1
            staging_target.parent.mkdir(parents=True, exist_ok=True)
            staging_target.write_bytes(data)
            extracted_paths.append(normalised)

    installed = InstalledMod(
        game_id=game.id,  # type: ignore[arg-type]
        name=parsed.name,
        staging_dir=safe_name,
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
        link_kind = (
            "junction"
            if rel_path.startswith("mods/") and "/" in rel_path[len("mods/") :]
            else "hardlink"
        )
        session.add(
            InstalledModFile(
                installed_mod_id=installed.id,  # type: ignore[arg-type]
                relative_path=rel_path,
                source_path=rel_path,
                link_kind=link_kind,
            )
        )

    session.commit()
    session.refresh(installed)

    if auto_deploy:
        from rippermod_manager.services.vfs import deploy_service

        deploy_service.deploy(game, session)

    # Index .archive files for resource-level conflict detection
    from rippermod_manager.services.archive_index_service import index_mod_archives

    _ = installed.files  # ensure files are loaded
    index_mod_archives(game, installed, session)
    session.commit()

    # Regenerate modlist.txt to include new archives in the load order
    from rippermod_manager.services.modlist_service import write_modlist

    write_modlist(game, session)

    logger.info(
        "Installed '%s' (%d files staged, %d overwritten in staging)",
        parsed.name,
        len(extracted_paths),
        overwritten,
    )
    from rippermod_manager.services.activity_service import record_activity

    record_activity(
        session,
        game_id=game.id,
        action="install",
        target=parsed.name,
        detail=f"{len(extracted_paths)} files",
    )
    return InstallResult(
        installed_mod_id=installed.id,  # type: ignore[arg-type]
        name=parsed.name,
        files_extracted=len(extracted_paths),
        files_skipped=skipped,
        files_overwritten=overwritten,
        installed_mod_name_safe=safe_name,
    )


def uninstall_mod(
    installed_mod: InstalledMod,
    game: Game,
    session: Session,
) -> UninstallResult:
    """Remove a mod's game-dir links and its staging subtree."""
    # Snapshot saves before this destructive change (best-effort, deduped).
    from rippermod_manager.services.save_backup_service import maybe_backup_before
    from rippermod_manager.services.vfs.primitives import (
        VfsError,
        remove_junction,
    )
    from rippermod_manager.services.vfs.primitives import unlink as vfs_unlink

    maybe_backup_before(game, session, reason="pre-uninstall")

    game_dir = Path(game.install_path)
    _ = installed_mod.files
    file_count = len(installed_mod.files)
    junction_dirs_seen: set[str] = set()

    for f in installed_mod.files:
        dst = game_dir / f.relative_path.replace("/", os.sep)
        if f.link_kind == "junction":
            parts = f.relative_path.replace("\\", "/").split("/")
            if len(parts) >= 2 and parts[0] == "mods":
                redmod_dst = game_dir / "mods" / parts[1]
                key = str(redmod_dst)
                if key in junction_dirs_seen:
                    continue
                junction_dirs_seen.add(key)
                try:
                    remove_junction(redmod_dst)
                except VfsError:
                    logger.warning("Could not remove junction %s", redmod_dst)
                continue
        try:
            vfs_unlink(dst)
        except VfsError:
            logger.warning("Could not unlink %s", dst)

    # Remove staging subtree
    if installed_mod.staging_dir:
        staging_dir = get_mods_dir(game) / installed_mod.staging_dir
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    # Existing DB cleanup
    from sqlalchemy import delete as sa_delete

    from rippermod_manager.models.load_order import LoadOrderPreference
    from rippermod_manager.models.profile import ProfileEntry
    from rippermod_manager.services.archive_index_service import remove_index_for_mod
    from rippermod_manager.services.modlist_service import write_modlist

    remove_index_for_mod(session, installed_mod.id)  # type: ignore[arg-type]

    mod_id = installed_mod.id
    session.exec(
        sa_delete(ProfileEntry).where(ProfileEntry.installed_mod_id == mod_id)  # type: ignore[arg-type]
    )
    session.exec(
        sa_delete(LoadOrderPreference).where(  # type: ignore[arg-type]
            (LoadOrderPreference.winner_mod_id == mod_id)
            | (LoadOrderPreference.loser_mod_id == mod_id)
        )
    )

    session.delete(installed_mod)
    session.commit()
    write_modlist(game, session)

    logger.info("Uninstalled '%s' (%d files removed)", installed_mod.name, file_count)
    from rippermod_manager.services.activity_service import record_activity

    record_activity(
        session,
        game_id=game.id,
        action="uninstall",
        target=installed_mod.name,
        detail=f"{file_count} files",
    )
    return UninstallResult(files_deleted=file_count, directories_removed=0)


def toggle_mod(
    installed_mod: InstalledMod,
    game: Game,
    session: Session,
    *,
    commit: bool = True,
) -> ToggleResult:
    """Flip ``installed_mod.disabled`` and deploy/undeploy that mod's files.

    Disable: removes game-dir hardlinks (staging untouched). The ``disabled``
    flag is the source of truth — no ``.disabled`` rename happens on disk.

    Enable: flips the flag, commits (so plan_deploy sees the enabled state),
    then builds a per-mod DeployPlan and executes it to recreate hardlinks.

    Pass ``commit=False`` to defer the DB commit (useful for batching in
    profile loads); the caller becomes responsible for commits.
    """
    from rippermod_manager.services.vfs.primitives import (
        VfsError,
        remove_junction,
    )
    from rippermod_manager.services.vfs.primitives import unlink as vfs_unlink

    game_dir = Path(game.install_path)
    should_disable = not installed_mod.disabled
    affected = 0

    _ = installed_mod.files  # touch relationship to load files

    if should_disable:
        # Snapshot saves before disabling (best-effort, deduped, CP2077 only).
        from rippermod_manager.services.save_backup_service import maybe_backup_before

        maybe_backup_before(game, session, reason="pre-disable")

        # Disable path: remove game-dir hardlinks, leave staging intact.
        junction_dirs_seen: set[str] = set()
        for f in installed_mod.files:
            dst = game_dir / f.relative_path.replace("/", os.sep)
            if f.link_kind == "junction":
                parts = f.relative_path.replace("\\", "/").split("/")
                if len(parts) >= 2 and parts[0] == "mods":
                    redmod_dst = game_dir / "mods" / parts[1]
                    key = str(redmod_dst)
                    if key in junction_dirs_seen:
                        continue
                    junction_dirs_seen.add(key)
                    try:
                        remove_junction(redmod_dst)
                        affected += 1
                    except VfsError:
                        logger.warning("Could not remove junction %s", redmod_dst)
                    continue
            try:
                if dst.exists():
                    vfs_unlink(dst)
                    affected += 1
            except VfsError:
                logger.warning("Could not unlink %s", dst)
        installed_mod.deployed = False

    installed_mod.disabled = should_disable
    session.add(installed_mod)
    if commit:
        session.commit()

    if not should_disable:
        # Re-enable path: build a per-mod plan and execute it.
        # Using an inline plan (not deploy_service.deploy()) to avoid producing
        # journal "failed" entries for already-deployed sibling mods. Same
        # verify_link / is_dir idempotency guard as plan_deploy so a re-enable
        # on already-linked files is a no-op instead of an AlreadyExistsError.
        from rippermod_manager.schemas.deploy import DeployOp, DeployPlan
        from rippermod_manager.services.vfs.deploy_service import execute_plan, pre_flight_check
        from rippermod_manager.services.vfs.primitives import verify_link

        pre = pre_flight_check(game)
        if pre.ok:
            staging_root = get_mods_dir(game)
            ops: list[DeployOp] = []
            junction_dirs_seen_enable: set[str] = set()
            for f in installed_mod.files:
                src = staging_root / installed_mod.staging_dir / f.source_path.replace("\\", "/")
                dst = game_dir / f.relative_path.replace("\\", "/")
                if f.link_kind == "junction":
                    parts = f.relative_path.replace("\\", "/").split("/")
                    if len(parts) >= 2 and parts[0] == "mods":
                        redmod_dst = game_dir / "mods" / parts[1]
                        redmod_src = staging_root / installed_mod.staging_dir / "mods" / parts[1]
                        key = str(redmod_dst)
                        if key in junction_dirs_seen_enable:
                            continue
                        junction_dirs_seen_enable.add(key)
                        # Idempotency: junction already in place.
                        if redmod_dst.is_dir():
                            continue
                        ops.append(
                            DeployOp(
                                operation="junction",
                                src=str(redmod_src),
                                dst=str(redmod_dst),
                                installed_mod_id=installed_mod.id,
                            )
                        )
                        continue
                # Idempotency: hardlink already points to the staged source.
                if verify_link(src, dst):
                    continue
                ops.append(
                    DeployOp(
                        operation="link",
                        src=str(src),
                        dst=str(dst),
                        installed_mod_id=installed_mod.id,
                    )
                )

            plan = DeployPlan(game_id=game.id, ops=ops)
            report = execute_plan(plan, session)
            if report.is_clean:
                installed_mod.deployed = True
                session.add(installed_mod)
                if commit:
                    session.commit()
            affected = report.done

    if commit:
        session.commit()

    from rippermod_manager.services.modlist_service import write_modlist

    write_modlist(game, session)

    action = "Disabled" if should_disable else "Enabled"
    logger.info("%s '%s' (%d files affected)", action, installed_mod.name, affected)
    if commit:
        from rippermod_manager.services.activity_service import record_activity

        record_activity(
            session,
            game_id=game.id,
            action="disable" if should_disable else "enable",
            target=installed_mod.name,
            detail=f"{affected} files",
        )
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
    except httpx.HTTPError:
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


def delete_archive(game: Game, filename: str) -> ArchiveDeleteResult:
    """Delete a single archive file from the staging folder.

    Validates the filename to prevent path traversal attacks.
    """
    staging = get_mods_dir(game)
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
    staging = get_mods_dir(game)
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
    staging = get_mods_dir(game)

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


def reparse_installed_mods(game_id: int, session: Session) -> int:
    """Re-parse source_archive filenames and update stale InstalledMod metadata.

    Compares the current parser output against stored ``name``,
    ``nexus_mod_id``, ``installed_version``, and ``upload_timestamp``.
    Updates any fields that differ.  Returns the number of mods updated.
    """
    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game_id,
            InstalledMod.source_archive != "",
        )
    ).all()

    updated = 0
    for mod in mods:
        parsed = parse_mod_filename(mod.source_archive)
        changed = False

        if parsed.name and parsed.name != mod.name:
            mod.name = parsed.name
            changed = True
        if parsed.nexus_mod_id is not None and parsed.nexus_mod_id != mod.nexus_mod_id:
            mod.nexus_mod_id = parsed.nexus_mod_id
            changed = True
        if parsed.version and parsed.version != mod.installed_version:
            mod.installed_version = parsed.version
            changed = True
        if parsed.upload_timestamp and parsed.upload_timestamp != mod.upload_timestamp:
            mod.upload_timestamp = parsed.upload_timestamp
            changed = True

        if changed:
            session.add(mod)
            updated += 1
            logger.info(
                "Re-parsed InstalledMod %d (%s): name=%r, nexus_mod_id=%s, version=%s",
                mod.id,
                mod.source_archive,
                mod.name,
                mod.nexus_mod_id,
                mod.installed_version,
            )

    if updated:
        session.commit()
        logger.info("Re-parsed %d/%d installed mods for game %d", updated, len(mods), game_id)

    return updated
