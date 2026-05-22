import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from rippermod_manager.database import get_session
from rippermod_manager.schemas.save_backup import (
    RestoreRequest,
    SaveBackupActionResult,
    SaveBackupOut,
    SaveBackupStatus,
)
from rippermod_manager.services import save_backup_service as svc
from rippermod_manager.services.vfs.primitives import GameRunningError

logger = logging.getLogger(__name__)

# Plain `def` (not async): every handler does blocking filesystem I/O
# (copytree / directory walks), so Starlette runs it in a threadpool instead of
# stalling the event loop. See .claude/rules/backend.md.
router = APIRouter(prefix="/save-backups", tags=["save-backups"])


@router.get("/", response_model=SaveBackupStatus)
def get_status(session: Session = Depends(get_session)) -> SaveBackupStatus:
    """Toggle state, resolved save folder, and existing backups (most recent first)."""
    save_dir = svc.resolve_save_dir(session)
    return SaveBackupStatus(
        enabled=svc.is_enabled(session),
        save_dir=str(save_dir),
        save_dir_exists=save_dir.is_dir(),
        backups=[SaveBackupOut(**b) for b in svc.list_backups(session)],
    )


@router.post("/backup-now", response_model=SaveBackupActionResult)
def backup_now(session: Session = Depends(get_session)) -> SaveBackupActionResult:
    """Force a snapshot now (manual intent overrides the unchanged-saves dedupe)."""
    info = svc.create_backup(session, reason="manual", force=True)
    if info is None:
        raise HTTPException(
            status_code=409, detail="No Cyberpunk 2077 save folder was found to back up."
        )
    return SaveBackupActionResult(created=True, backup=SaveBackupOut(**info))


@router.post("/restore", response_model=SaveBackupActionResult)
def restore(
    body: RestoreRequest, session: Session = Depends(get_session)
) -> SaveBackupActionResult:
    try:
        result = svc.restore_backup(session, body.id)
    except GameRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SaveBackupActionResult(restored=True, restored_to=result["restored_to"])
