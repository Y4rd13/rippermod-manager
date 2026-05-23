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
    installed_mod_id: int | None = None,
    source_archive: str = "",
    prior_disabled: bool | None = None,
    undoable: bool = False,
) -> None:
    """Append a timestamped activity-log entry for a meaningful user action.

    Best-effort and self-contained: callers invoke it *after* their own action
    has been committed, so it commits its own row and never raises into the
    caller's flow -- a logging failure must not break installs/deploys/etc.
    Retention is enforced separately on read (prune_activity) so this write path
    stays a single insert.

    ``undoable`` plus the captured metadata (installed_mod_id / source_archive /
    prior_disabled) let the entry be reversed later via ``undo_entry``.
    """
    try:
        session.add(
            ActivityLog(
                game_id=game_id,
                action=action,
                target=target[:200],
                detail=detail[:200],
                status=status,
                installed_mod_id=installed_mod_id,
                source_archive=source_archive[:200],
                prior_disabled=prior_disabled,
                undoable=undoable,
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


class ActivityUndoError(Exception):
    """Raised when an activity entry can't be undone in the current state
    (mod gone, archive missing, name collision). The router maps it to 409."""


def undo_entry(session: Session, entry: ActivityLog, game) -> str:
    """Reverse the action recorded by ``entry`` (Tier A+B); return a short
    description of the inverse performed.

    - enable / disable -> toggle back to the state before the original action
    - install          -> uninstall
    - uninstall        -> reinstall from the original archive

    deploy / undeploy / download are recorded with ``undoable=False`` and never
    reach here. Raises ``ActivityUndoError`` when the current state no longer
    permits the undo (caller maps it to HTTP 409); never partially applies.
    """
    from rippermod_manager.models.install import InstalledMod
    from rippermod_manager.services import install_service

    action = entry.action
    if action in ("enable", "disable"):
        mod = (
            session.get(InstalledMod, entry.installed_mod_id)
            if entry.installed_mod_id is not None
            else None
        )
        if mod is None:
            raise ActivityUndoError("The mod is no longer installed.")
        # Restore the state captured before the original toggle. Binary, so one
        # toggle reaches it; a no-op if it's already in that state.
        if entry.prior_disabled is None or mod.disabled != entry.prior_disabled:
            install_service.toggle_mod(mod, game, session)
        return f"restored {mod.name}"
    if action == "install":
        mod = (
            session.get(InstalledMod, entry.installed_mod_id)
            if entry.installed_mod_id is not None
            else None
        )
        if mod is None:
            raise ActivityUndoError("The mod is no longer installed.")
        install_service.uninstall_mod(mod, game, session)
        return f"uninstalled {entry.target}"
    if action == "uninstall":
        if not entry.source_archive:
            raise ActivityUndoError("No source archive was recorded for this uninstall.")
        from rippermod_manager.services.paths import get_mods_dir

        archive_path = get_mods_dir(game) / entry.source_archive
        if not archive_path.exists():
            raise ActivityUndoError("The original archive is no longer available.")
        try:
            install_service.install_mod(game, archive_path, session)
        except (ValueError, FileNotFoundError) as exc:
            raise ActivityUndoError(str(exc)) from exc
        return f"reinstalled {entry.target}"
    raise ActivityUndoError("This action can't be undone.")
