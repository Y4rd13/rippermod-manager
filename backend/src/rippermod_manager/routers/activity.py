import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from rippermod_manager.database import get_session
from rippermod_manager.models.activity import ActivityLog
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.activity import ActivityLogOut
from rippermod_manager.services.activity_service import (
    ActivityUndoError,
    prune_activity,
    record_activity,
    undo_entry,
)

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


@router.post("/{entry_id}/undo", response_model=ActivityLogOut)
def undo_activity(
    game_name: str,
    entry_id: int,
    session: Session = Depends(get_session),
) -> ActivityLog:
    """Reverse a previously recorded action (Tier A+B): enable/disable/install
    are clean inverses; uninstall reinstalls from the original archive. Returns
    the entry with ``undone_at`` set, and records the inverse as its own row.

    404 if the entry isn't for this game; 409 if it isn't undoable, was already
    undone, or the current state no longer permits it (mod gone, archive gone).

    Plain ``def``: undo runs blocking install/uninstall work, so Starlette
    threadpools it off the event loop.
    """
    game = get_game_or_404(game_name, session)
    entry = session.get(ActivityLog, entry_id)
    if entry is None or entry.game_id != game.id:
        raise HTTPException(status_code=404, detail="Activity entry not found.")
    if not entry.undoable or entry.undone_at is not None:
        raise HTTPException(status_code=409, detail="This entry can't be undone.")
    try:
        summary = undo_entry(session, entry, game)
    except ActivityUndoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    entry.undone_at = datetime.now(UTC)
    session.add(entry)
    session.commit()
    # Append the inverse as its own (non-undoable) row -- keeps the log a
    # faithful append-only history.
    record_activity(
        session,
        game_id=game.id,
        action="undo",
        target=summary,
        detail=f"undo of {entry.action}",
    )
    session.refresh(entry)
    return entry
