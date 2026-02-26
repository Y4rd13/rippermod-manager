"""Endpoints for cross-mod conflict graph visualization."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from rippermod_manager.database import get_session
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.conflicts import ConflictGraphResult
from rippermod_manager.services.conflict_graph_service import build_conflict_graph

router = APIRouter(prefix="/games/{game_name}/conflicts", tags=["conflicts"])


@router.get("/graph", response_model=ConflictGraphResult)
async def conflict_graph(
    game_name: str,
    session: Session = Depends(get_session),
) -> ConflictGraphResult:
    """Build a conflict graph across all installed mods and uninstalled archives."""
    game = get_game_or_404(game_name, session)
    return build_conflict_graph(game, session)
