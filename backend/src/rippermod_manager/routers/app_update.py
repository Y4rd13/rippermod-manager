"""Self-update endpoints for RipperMod Manager itself.

POST /api/v1/app-update/download — start (or join) a Premium in-app download
of the latest installer. The response always returns the current status, so
the frontend can poll via GET and react to state transitions.

The backend never auto-launches the installer — the frontend surfaces an
"Open Folder" button so the user runs the .exe themselves. See
docs/nexus-compliance.md for the auto-update policy this respects.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from rippermod_manager.config import settings
from rippermod_manager.database import get_session
from rippermod_manager.services import app_update_service
from rippermod_manager.services.settings_helpers import get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app-update", tags=["app-update"])


class AppUpdateStatusOut(BaseModel):
    state: Literal["idle", "downloading", "ready", "error"]
    version: str | None = None
    file_name: str | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _to_out(status: app_update_service.AppUpdateStatus) -> AppUpdateStatusOut:
    return AppUpdateStatusOut(
        state=status.state,
        version=status.version,
        file_name=status.file_name,
        downloaded_bytes=status.downloaded_bytes,
        total_bytes=status.total_bytes,
        path=status.path,
        error_code=status.error_code,
        error_message=status.error_message,
    )


@router.get("/download", response_model=AppUpdateStatusOut)
async def get_download_status() -> AppUpdateStatusOut:
    return _to_out(app_update_service.get_status())


@router.post("/download", response_model=AppUpdateStatusOut)
async def start_download(session: Session = Depends(get_session)) -> AppUpdateStatusOut:
    api_key = get_setting(session, "nexus_api_key")
    status = await app_update_service.start_download(api_key, settings.data_dir)
    return _to_out(status)


@router.post("/download/cancel", response_model=AppUpdateStatusOut)
async def cancel_download() -> AppUpdateStatusOut:
    status = await app_update_service.cancel()
    return _to_out(status)
