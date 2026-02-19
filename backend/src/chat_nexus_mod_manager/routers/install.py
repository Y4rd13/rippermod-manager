"""Endpoints for mod installation, uninstallation, enable/disable, and conflict checking."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.matching.filename_parser import parse_mod_filename
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.schemas.install import (
    AvailableArchive,
    ConflictCheckResult,
    InstalledModOut,
    InstallRequest,
    InstallResult,
    ToggleResult,
    UninstallResult,
)
from chat_nexus_mod_manager.services.conflict_service import check_conflicts
from chat_nexus_mod_manager.services.install_service import (
    install_mod,
    list_available_archives,
    toggle_mod,
    uninstall_mod,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/install", tags=["install"])


def _get_game(game_name: str, session: Session) -> Game:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")
    return game


@router.get("/available", response_model=list[AvailableArchive])
def list_archives(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[AvailableArchive]:
    """List mod archives available for installation."""
    game = _get_game(game_name, session)
    archives = list_available_archives(game)
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
            )
        )
    return result


@router.get("/installed", response_model=list[InstalledModOut])
def list_installed(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[InstalledModOut]:
    """List all installed mods for a game."""
    game = _get_game(game_name, session)
    mods = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()
    result: list[InstalledModOut] = []
    for mod in mods:
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
            )
        )
    return result


@router.post("/", response_model=InstallResult, status_code=201)
def install(
    game_name: str,
    data: InstallRequest,
    session: Session = Depends(get_session),
) -> InstallResult:
    """Install a mod from an archive in the staging folder."""
    game = _get_game(game_name, session)
    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / data.archive_filename
    if not archive_path.is_file():
        raise HTTPException(404, f"Archive not found: {data.archive_filename}")

    try:
        return install_mod(game, archive_path, session, data.skip_conflicts)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/installed/{mod_id}", response_model=UninstallResult)
def uninstall(
    game_name: str,
    mod_id: int,
    session: Session = Depends(get_session),
) -> UninstallResult:
    """Uninstall a mod, removing all its files from the game directory."""
    game = _get_game(game_name, session)
    mod = session.get(InstalledMod, mod_id)
    if not mod or mod.game_id != game.id:
        raise HTTPException(404, "Installed mod not found")
    return uninstall_mod(mod, game, session)


@router.patch("/installed/{mod_id}/toggle", response_model=ToggleResult)
def toggle(
    game_name: str,
    mod_id: int,
    session: Session = Depends(get_session),
) -> ToggleResult:
    """Enable or disable a mod by renaming its files."""
    game = _get_game(game_name, session)
    mod = session.get(InstalledMod, mod_id)
    if not mod or mod.game_id != game.id:
        raise HTTPException(404, "Installed mod not found")
    return toggle_mod(mod, game, session)


@router.get("/conflicts", response_model=ConflictCheckResult)
def conflicts(
    game_name: str,
    archive_filename: str,
    session: Session = Depends(get_session),
) -> ConflictCheckResult:
    """Check for file conflicts before installing an archive."""
    game = _get_game(game_name, session)
    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / archive_filename
    if not archive_path.is_file():
        raise HTTPException(404, f"Archive not found: {archive_filename}")
    return check_conflicts(game, archive_path, session)
