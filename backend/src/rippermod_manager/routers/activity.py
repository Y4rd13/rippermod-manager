import logging

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from rippermod_manager.database import get_session
from rippermod_manager.models.activity import ActivityLog
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.activity import ActivityLogOut
from rippermod_manager.services.activity_service import prune_activity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/activity", tags=["activity"])


@router.get("/", response_model=list[ActivityLogOut])
async def list_activity(
    game_name: str,
    limit: int = 200,
    session: Session = Depends(get_session),
) -> list[ActivityLog]:
    """Most-recent-first activity history for the game (ordered by id).

    Enforces the per-game retention cap opportunistically here so the write
    path (record_activity) stays a single insert.
    """
    game = get_game_or_404(game_name, session)
    prune_activity(session, game.id)
    limit = max(1, min(limit, 1000))
    rows = session.exec(
        select(ActivityLog)
        .where(ActivityLog.game_id == game.id)
        .order_by(col(ActivityLog.id).desc())
        .limit(limit)
    ).all()
    return list(rows)
