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
from rippermod_manager.services.load_order import apply_prefer_mod, get_archive_load_order

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/load-order", tags=["load-order"])


def _get_mod_pair(
    game_name: str,
    data: PreferModRequest,
    session: Session,
) -> tuple[Game, InstalledMod, InstalledMod]:
    """Validate and return ``(game, winner_mod, loser_mod)``."""
    game = get_game_or_404(game_name, session)

    if data.winner_mod_id == data.loser_mod_id:
        raise HTTPException(400, "winner_mod_id and loser_mod_id must differ")

    winner = session.get(InstalledMod, data.winner_mod_id)
    if not winner or winner.game_id != game.id:
        raise HTTPException(404, f"Winner mod {data.winner_mod_id} not found for this game")

    loser = session.get(InstalledMod, data.loser_mod_id)
    if not loser or loser.game_id != game.id:
        raise HTTPException(404, f"Loser mod {data.loser_mod_id} not found for this game")

    if winner.disabled:
        raise HTTPException(400, f"Winner mod '{winner.name}' is disabled")
    if loser.disabled:
        raise HTTPException(400, f"Loser mod '{loser.name}' is disabled")

    return game, winner, loser


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
    """Dry-run of the prefer action — returns planned renames without executing."""
    game, winner, loser = _get_mod_pair(game_name, data, session)
    return apply_prefer_mod(winner, loser, game, session, dry_run=True)


@router.post("/prefer", response_model=PreferModResult)
async def prefer(
    game_name: str,
    data: PreferModRequest,
    session: Session = Depends(get_session),
) -> PreferModResult:
    """Execute archive renames so the winner mod loads after the loser."""
    game, winner, loser = _get_mod_pair(game_name, data, session)
    return apply_prefer_mod(winner, loser, game, session)
