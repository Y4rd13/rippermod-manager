"""Endpoints for archive load-order inspection and conflict resolution."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.load_order import (
    LoadOrderResult,
    PreferModRequest,
    PreferModResult,
)
from rippermod_manager.services.load_order import get_archive_load_order
from rippermod_manager.services.modlist_service import add_preferences, generate_modlist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/load-order", tags=["load-order"])


def _validate_prefer_request(
    game_name: str,
    data: PreferModRequest,
    session: Session,
) -> tuple[Game, InstalledMod, list[InstalledMod]]:
    """Validate and return ``(game, winner_mod, loser_mods)``."""
    game = get_game_or_404(game_name, session)

    winner = session.get(InstalledMod, data.winner_mod_id)
    if not winner or winner.game_id != game.id:
        raise HTTPException(404, f"Winner mod {data.winner_mod_id} not found for this game")
    if winner.disabled:
        raise HTTPException(400, f"Winner mod '{winner.name}' is disabled")

    if not data.loser_mod_ids:
        raise HTTPException(400, "At least one loser_mod_id is required")

    loser_mods: list[InstalledMod] = []
    for loser_id in data.loser_mod_ids:
        if loser_id == data.winner_mod_id:
            raise HTTPException(400, "winner_mod_id and loser_mod_id must differ")
        loser = session.get(InstalledMod, loser_id)
        if not loser or loser.game_id != game.id:
            raise HTTPException(404, f"Loser mod {loser_id} not found for this game")
        if loser.disabled:
            raise HTTPException(400, f"Loser mod '{loser.name}' is disabled")
        loser_mods.append(loser)

    return game, winner, loser_mods


@router.get("/", response_model=LoadOrderResult)
async def load_order(
    game_name: str,
    session: Session = Depends(get_session),
) -> LoadOrderResult:
    """Return the full archive load order and detected conflicts."""
    game = get_game_or_404(game_name, session)
    return get_archive_load_order(game, session)


@router.post("/prefer/preview", response_model=PreferModResult)
async def prefer_preview(
    game_name: str,
    data: PreferModRequest,
    session: Session = Depends(get_session),
) -> PreferModResult:
    """Dry-run: show what preferences would be added without writing modlist.txt."""
    game, winner, loser_mods = _validate_prefer_request(game_name, data, session)
    modlist = generate_modlist(game, session)
    loser_names = [m.name for m in loser_mods]
    return PreferModResult(
        success=True,
        message=(
            f"Will prefer '{winner.name}' over {', '.join(repr(n) for n in loser_names)}. "
            f"modlist.txt will be updated ({len(modlist)} entries currently)."
        ),
        preferences_added=len(loser_mods),
        modlist_entries=len(modlist),
        dry_run=True,
    )


@router.post("/prefer", response_model=PreferModResult)
async def prefer(
    game_name: str,
    data: PreferModRequest,
    session: Session = Depends(get_session),
) -> PreferModResult:
    """Add load-order preferences and write modlist.txt."""
    game, winner, loser_mods = _validate_prefer_request(game_name, data, session)
    loser_ids = [m.id for m in loser_mods]  # type: ignore[misc]
    added = add_preferences(game.id, data.winner_mod_id, loser_ids, game, session)  # type: ignore[arg-type]
    modlist = generate_modlist(game, session)
    loser_names = [m.name for m in loser_mods]
    return PreferModResult(
        success=True,
        message=(
            f"Preferred '{winner.name}' over {', '.join(repr(n) for n in loser_names)}. "
            f"{added} preference(s) added, modlist.txt has {len(modlist)} entries."
        ),
        preferences_added=added,
        modlist_entries=len(modlist),
        dry_run=False,
    )
