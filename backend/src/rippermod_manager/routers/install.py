"""Endpoints for mod installation, uninstallation, enable/disable, and conflict checking."""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from rippermod_manager.database import get_session
from rippermod_manager.matching.filename_parser import parse_mod_filename
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusDownload, NexusModMeta
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.install import (
    ArchiveContentsResult,
    ArchiveDeleteResult,
    ArchiveEntryOut,
    ArchiveFileEntry,
    ArchivePreviewResult,
    AvailableArchive,
    ConflictCheckResult,
    InstalledModOut,
    InstallRequest,
    InstallResult,
    OrphanCleanupResult,
    ToggleResult,
    UninstallResult,
)
from rippermod_manager.schemas.redscript import RedscriptConflictResult
from rippermod_manager.services.conflict_service import check_conflicts
from rippermod_manager.services.download_dates import archive_download_dates
from rippermod_manager.services.install_service import (
    delete_archive,
    delete_orphaned_archives,
    install_mod,
    list_available_archives,
    resolve_installed_file_id,
    toggle_mod,
    uninstall_mod,
)
from rippermod_manager.services.redscript_analysis import check_redscript_conflicts
from rippermod_manager.services.settings_helpers import get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/install", tags=["install"])


@router.get("/available", response_model=list[AvailableArchive])
async def list_archives(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[AvailableArchive]:
    """List mod archives available for installation."""
    game = get_game_or_404(game_name, session)
    archives = list_available_archives(game)

    installed_archives: dict[str, int] = {}
    rows = session.exec(
        select(InstalledMod.source_archive, InstalledMod.id).where(
            InstalledMod.game_id == game.id,
            InstalledMod.source_archive != "",
        )
    ).all()
    for sa, mod_id in rows:
        if sa not in installed_archives:
            installed_archives[sa] = mod_id

    archive_names = {p.name for p in archives}
    dl_date_map = archive_download_dates(
        session,
        game.id,
        game.install_path,
        archive_names,  # type: ignore[arg-type]
    )

    result: list[AvailableArchive] = []
    for path in archives:
        parsed = parse_mod_filename(path.name)
        stat = path.stat()
        dl_date = dl_date_map.get(path.name)
        result.append(
            AvailableArchive(
                filename=path.name,
                size=stat.st_size,
                nexus_mod_id=parsed.nexus_mod_id,
                parsed_name=parsed.name,
                parsed_version=parsed.version,
                is_installed=path.name in installed_archives,
                installed_mod_id=installed_archives.get(path.name),
                last_downloaded_at=dl_date,
                is_empty=stat.st_size == 0,
            )
        )
    return result


@router.get("/installed", response_model=list[InstalledModOut])
async def list_installed(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[InstalledModOut]:
    """List all installed mods for a game."""
    game = get_game_or_404(game_name, session)

    rows = session.exec(
        select(InstalledMod, NexusModMeta, NexusDownload)
        .outerjoin(
            NexusModMeta,
            InstalledMod.nexus_mod_id == NexusModMeta.nexus_mod_id,
        )
        .outerjoin(
            NexusDownload,
            (InstalledMod.nexus_mod_id == NexusDownload.nexus_mod_id)
            & (NexusDownload.game_id == game.id),
        )
        .where(InstalledMod.game_id == game.id)
    ).all()

    source_archives = {mod.source_archive for mod, _, _ in rows if mod.source_archive}
    dl_date_map = archive_download_dates(
        session,
        game.id,
        game.install_path,
        source_archives,  # type: ignore[arg-type]
    )

    seen: set[int] = set()
    result: list[InstalledModOut] = []
    for mod, meta, ndl in rows:
        mod_id: int = mod.id  # type: ignore[assignment]
        if mod_id in seen:
            continue
        seen.add(mod_id)
        _ = mod.files
        dl_date = dl_date_map.get(mod.source_archive) if mod.source_archive else None
        result.append(
            InstalledModOut(
                id=mod_id,
                name=mod.name,
                source_archive=mod.source_archive,
                nexus_mod_id=mod.nexus_mod_id,
                installed_version=mod.installed_version,
                disabled=mod.disabled,
                installed_at=mod.installed_at,
                file_count=len(mod.files),
                mod_group_id=mod.mod_group_id,
                nexus_updated_at=meta.updated_at if meta else None,
                nexus_name=meta.name if meta else None,
                summary=meta.summary if meta else None,
                author=meta.author if meta else None,
                endorsement_count=meta.endorsement_count if meta else None,
                picture_url=meta.picture_url if meta else None,
                category=meta.category if meta else None,
                last_downloaded_at=dl_date,
                nexus_url=(
                    f"https://www.nexusmods.com/{game.domain_name}/mods/{mod.nexus_mod_id}"
                    if mod.nexus_mod_id
                    else None
                ),
                is_tracked=ndl.is_tracked if ndl else False,
                is_endorsed=ndl.is_endorsed if ndl else False,
            )
        )
    return result


@router.post("/", response_model=InstallResult, status_code=201)
async def install(
    game_name: str,
    data: InstallRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> InstallResult:
    """Install a mod from an archive in the staging folder."""
    game = get_game_or_404(game_name, session)
    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / data.archive_filename
    if not archive_path.resolve().is_relative_to(staging.resolve()):
        raise HTTPException(400, "Invalid archive filename")
    if not archive_path.is_file():
        raise HTTPException(404, f"Archive not found: {data.archive_filename}")

    try:
        result = install_mod(game, archive_path, session, data.skip_conflicts, data.file_renames)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    # Best-effort background resolution of nexus_file_id (does not block response)
    api_key = get_setting(session, "nexus_api_key")
    if api_key:
        installed = session.get(InstalledMod, result.installed_mod_id)
        if installed and not installed.nexus_file_id and installed.nexus_mod_id:
            background_tasks.add_task(
                resolve_installed_file_id,
                result.installed_mod_id,
                game.domain_name,
                installed.nexus_mod_id,
                installed.source_archive,
                api_key,
            )

    return result


@router.delete("/installed/{mod_id}", response_model=UninstallResult)
async def uninstall(
    game_name: str,
    mod_id: int,
    session: Session = Depends(get_session),
) -> UninstallResult:
    """Uninstall a mod, removing all its files from the game directory."""
    game = get_game_or_404(game_name, session)
    mod = session.get(InstalledMod, mod_id)
    if not mod or mod.game_id != game.id:
        raise HTTPException(404, "Installed mod not found")
    return uninstall_mod(mod, game, session)


@router.patch("/installed/{mod_id}/toggle", response_model=ToggleResult)
async def toggle(
    game_name: str,
    mod_id: int,
    session: Session = Depends(get_session),
) -> ToggleResult:
    """Enable or disable a mod by renaming its files."""
    game = get_game_or_404(game_name, session)
    mod = session.get(InstalledMod, mod_id)
    if not mod or mod.game_id != game.id:
        raise HTTPException(404, "Installed mod not found")
    return toggle_mod(mod, game, session)


@router.get("/preview", response_model=ArchivePreviewResult)
async def preview_archive(
    game_name: str,
    archive_filename: str,
    session: Session = Depends(get_session),
) -> ArchivePreviewResult:
    """List the processed files that would be extracted from an archive."""
    from rippermod_manager.archive.handler import open_archive
    from rippermod_manager.services.archive_layout import (
        ArchiveLayout,
        detect_layout,
        known_roots_for_game,
    )

    game = get_game_or_404(game_name, session)
    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / archive_filename
    if not archive_path.resolve().is_relative_to(staging.resolve()):
        raise HTTPException(400, "Invalid archive filename")
    if not archive_path.is_file():
        raise HTTPException(404, f"Archive not found: {archive_filename}")

    try:
        with open_archive(archive_path) as archive:
            all_entries = archive.list_entries()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(422, str(exc)) from exc

    known_roots = known_roots_for_game(game.domain_name)
    layout_result = detect_layout(all_entries, known_roots)
    is_fomod = layout_result.layout == ArchiveLayout.FOMOD
    strip_prefix = layout_result.strip_prefix

    files: list[ArchiveFileEntry] = []
    for entry in all_entries:
        if entry.is_dir:
            continue
        normalised = entry.filename.replace("\\", "/")
        if strip_prefix:
            if normalised.startswith(strip_prefix + "/"):
                normalised = normalised[len(strip_prefix) + 1 :]
            else:
                continue
        files.append(ArchiveFileEntry(file_path=normalised, size=entry.size, is_dir=False))

    return ArchivePreviewResult(
        archive_filename=archive_filename,
        total_files=len(files),
        is_fomod=is_fomod,
        files=files,
    )


@router.get("/conflicts", response_model=ConflictCheckResult)
async def conflicts(
    game_name: str,
    archive_filename: str,
    session: Session = Depends(get_session),
) -> ConflictCheckResult:
    """Check for file conflicts before installing an archive."""
    game = get_game_or_404(game_name, session)
    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / archive_filename
    if not archive_path.resolve().is_relative_to(staging.resolve()):
        raise HTTPException(400, "Invalid archive filename")
    if not archive_path.is_file():
        raise HTTPException(404, f"Archive not found: {archive_filename}")
    return check_conflicts(game, archive_path, session)


@router.delete("/archives/{filename}", response_model=ArchiveDeleteResult)
async def delete_archive_endpoint(
    game_name: str,
    filename: str,
    session: Session = Depends(get_session),
) -> ArchiveDeleteResult:
    """Delete a single archive file from the staging folder."""
    game = get_game_or_404(game_name, session)
    return delete_archive(game.install_path, filename)


@router.post("/archives/cleanup-orphans", response_model=OrphanCleanupResult)
async def cleanup_orphans(
    game_name: str,
    session: Session = Depends(get_session),
) -> OrphanCleanupResult:
    """Delete all archives not referenced by any installed mod or active download."""
    game = get_game_or_404(game_name, session)
    return delete_orphaned_archives(game, session)


@router.get("/archives/{filename}/contents", response_model=ArchiveContentsResult)
async def archive_contents(
    game_name: str,
    filename: str,
    session: Session = Depends(get_session),
) -> ArchiveContentsResult:
    """List the hierarchical file tree inside an archive."""
    from rippermod_manager.archive.handler import open_archive

    game = get_game_or_404(game_name, session)
    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / filename
    if not archive_path.resolve().is_relative_to(staging.resolve()):
        raise HTTPException(400, "Invalid archive filename")
    if not archive_path.is_file():
        raise HTTPException(404, f"Archive not found: {filename}")

    try:
        with open_archive(archive_path) as archive:
            entries = archive.list_entries()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(422, str(exc)) from exc

    total_files = sum(1 for e in entries if not e.is_dir)
    total_size = sum(e.size for e in entries if not e.is_dir)

    # Build nested dict tree from flat entries
    root: dict = {}
    for entry in entries:
        parts = entry.filename.replace("\\", "/").strip("/").split("/")
        node = root
        for part in parts:
            if part not in node:
                node[part] = {}
            node = node[part]
        if not entry.is_dir:
            node["\x00size"] = entry.size

    def dict_to_tree(d: dict) -> list[ArchiveEntryOut]:
        dirs: list[ArchiveEntryOut] = []
        files: list[ArchiveEntryOut] = []
        for name, value in d.items():
            if name == "\x00size":
                continue
            is_dir = any(k != "\x00size" for k in value)
            if is_dir:
                dirs.append(ArchiveEntryOut(name=name, is_dir=True, children=dict_to_tree(value)))
            else:
                files.append(
                    ArchiveEntryOut(name=name, is_dir=False, size=value.get("\x00size", 0))
                )
        dirs.sort(key=lambda x: x.name.lower())
        files.sort(key=lambda x: x.name.lower())
        return dirs + files

    return ArchiveContentsResult(
        filename=filename,
        total_files=total_files,
        total_size=total_size,
        tree=dict_to_tree(root),
    )


@router.get("/redscript-conflicts", response_model=RedscriptConflictResult)
async def redscript_conflicts(
    game_name: str,
    session: Session = Depends(get_session),
) -> RedscriptConflictResult:
    """Analyze installed redscript mods for annotation-level conflicts."""
    game = get_game_or_404(game_name, session)
    return check_redscript_conflicts(game, session)
