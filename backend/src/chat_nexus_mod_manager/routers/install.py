"""Endpoints for mod installation, uninstallation, enable/disable, and conflict checking."""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.matching.filename_parser import parse_mod_filename
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.nexus import NexusModMeta
from chat_nexus_mod_manager.routers.deps import get_game_or_404
from chat_nexus_mod_manager.schemas.install import (
    ArchiveDeleteResult,
    AvailableArchive,
    ConflictCheckResult,
    InstalledModOut,
    InstallRequest,
    InstallResult,
    OrphanCleanupResult,
    ToggleResult,
    UninstallResult,
)
from chat_nexus_mod_manager.services.conflict_service import check_conflicts
from chat_nexus_mod_manager.services.install_service import (
    delete_archive,
    delete_orphaned_archives,
    install_mod,
    list_available_archives,
    resolve_installed_file_id,
    toggle_mod,
    uninstall_mod,
)
from chat_nexus_mod_manager.services.settings_helpers import get_setting

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

    installed_archives: set[str] = set()
    rows = session.exec(
        select(InstalledMod.source_archive).where(
            InstalledMod.game_id == game.id,
            InstalledMod.source_archive != "",
        )
    ).all()
    for sa in rows:
        installed_archives.add(sa)

    result: list[AvailableArchive] = []
    for path in archives:
        parsed = parse_mod_filename(path.name)
        result.append(
            AvailableArchive(
                filename=path.name,
                size=path.stat().st_size,
                nexus_mod_id=parsed.nexus_mod_id,
                parsed_name=parsed.name,
                parsed_version=parsed.version,
                is_installed=path.name in installed_archives,
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
        select(InstalledMod, NexusModMeta)
        .outerjoin(
            NexusModMeta,
            InstalledMod.nexus_mod_id == NexusModMeta.nexus_mod_id,
        )
        .where(InstalledMod.game_id == game.id)
    ).all()

    result: list[InstalledModOut] = []
    for mod, meta in rows:
        _ = mod.files
        result.append(
            InstalledModOut(
                id=mod.id,  # type: ignore[arg-type]
                name=mod.name,
                source_archive=mod.source_archive,
                nexus_mod_id=mod.nexus_mod_id,
                installed_version=mod.installed_version,
                disabled=mod.disabled,
                installed_at=mod.installed_at,
                file_count=len(mod.files),
                mod_group_id=mod.mod_group_id,
                nexus_updated_at=meta.updated_at if meta else None,
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
        result = install_mod(game, archive_path, session, data.skip_conflicts)
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
