"""Endpoints for mod profile management: save, load, export, import."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.profile import Profile
from chat_nexus_mod_manager.routers.deps import get_game_or_404
from chat_nexus_mod_manager.schemas.profile import (
    ProfileCreate,
    ProfileExport,
    ProfileOut,
)
from chat_nexus_mod_manager.services.profile_service import (
    create_profile,
    delete_profile,
    export_profile,
    import_profile,
    list_profiles,
    load_profile,
    profile_to_out,
)

router = APIRouter(prefix="/games/{game_name}/profiles", tags=["profiles"])


def _get_profile(profile_id: int, game: Game, session: Session) -> Profile:
    profile = session.get(Profile, profile_id)
    if not profile or profile.game_id != game.id:
        raise HTTPException(404, "Profile not found")
    return profile


@router.get("/", response_model=list[ProfileOut])
async def list_game_profiles(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[ProfileOut]:
    """List all saved profiles for a game."""
    game = get_game_or_404(game_name, session)
    return list_profiles(game, session)


@router.post("/", response_model=ProfileOut, status_code=201)
async def save_profile(
    game_name: str,
    data: ProfileCreate,
    session: Session = Depends(get_session),
) -> ProfileOut:
    """Save a profile from the current installed mod state."""
    game = get_game_or_404(game_name, session)
    return create_profile(game, data, session)


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(
    game_name: str,
    profile_id: int,
    session: Session = Depends(get_session),
) -> ProfileOut:
    """Get a profile with its mod list."""
    game = get_game_or_404(game_name, session)
    profile = _get_profile(profile_id, game, session)
    _ = profile.entries
    return profile_to_out(profile, session)


@router.delete("/{profile_id}", status_code=204)
async def remove_profile(
    game_name: str,
    profile_id: int,
    session: Session = Depends(get_session),
) -> None:
    """Delete a profile."""
    game = get_game_or_404(game_name, session)
    profile = _get_profile(profile_id, game, session)
    delete_profile(profile, session)


@router.post("/{profile_id}/load", response_model=ProfileOut)
async def apply_profile(
    game_name: str,
    profile_id: int,
    session: Session = Depends(get_session),
) -> ProfileOut:
    """Load a profile, enabling/disabling mods to match the saved state."""
    game = get_game_or_404(game_name, session)
    profile = _get_profile(profile_id, game, session)
    return load_profile(profile, game, session)


@router.post("/{profile_id}/export", response_model=ProfileExport)
async def export_game_profile(
    game_name: str,
    profile_id: int,
    session: Session = Depends(get_session),
) -> ProfileExport:
    """Export a profile as a shareable JSON object."""
    game = get_game_or_404(game_name, session)
    profile = _get_profile(profile_id, game, session)
    return export_profile(profile, game, session)


@router.post("/import", response_model=ProfileOut, status_code=201)
async def import_game_profile(
    game_name: str,
    data: ProfileExport,
    session: Session = Depends(get_session),
) -> ProfileOut:
    """Import a profile from an exported JSON object."""
    game = get_game_or_404(game_name, session)
    return import_profile(game, data, session)
