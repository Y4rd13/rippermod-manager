import logging

from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select

from rippermod_manager.models.activity import ActivityLog

logger = logging.getLogger(__name__)

# Per-game retention cap; enforced opportunistically on read (see prune_activity).
MAX_ENTRIES_PER_GAME = 1000


def record_activity(
    session: Session,
    *,
    game_id: int,
    action: str,
    target: str = "",
    detail: str = "",
    status: str = "success",
) -> None:
    """Append a timestamped activity-log entry for a meaningful user action.

    Best-effort and self-contained: callers invoke it *after* their own action
    has been committed, so it commits its own row and never raises into the
    caller's flow -- a logging failure must not break installs/deploys/etc.
    Retention is enforced separately on read (prune_activity) so this write path
    stays a single insert.
    """
    try:
        session.add(
            ActivityLog(
                game_id=game_id,
                action=action,
                target=target[:200],
                detail=detail[:200],
                status=status,
            )
        )
        session.commit()
    except SQLAlchemyError:
        logger.warning("Failed to record activity '%s' for game %s", action, game_id, exc_info=True)
        session.rollback()


def prune_activity(session: Session, game_id: int) -> None:
    """Delete rows older than the MAX_ENTRIES_PER_GAME most recent (by id) for the game.

    Called opportunistically on read so the per-write path stays a single insert
    (mirrors download_service.cleanup_old_jobs).
    """
    cutoff_id = session.exec(
        select(ActivityLog.id)
        .where(ActivityLog.game_id == game_id)
        .order_by(col(ActivityLog.id).desc())
        .offset(MAX_ENTRIES_PER_GAME - 1)
        .limit(1)
    ).first()
    if cutoff_id is None:
        return
    session.exec(
        sa_delete(ActivityLog).where(  # type: ignore[arg-type]
            ActivityLog.game_id == game_id,
            col(ActivityLog.id) < cutoff_id,
        )
    )
    session.commit()
