from __future__ import annotations

import logging
import os
from datetime import UTC
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.download import DownloadJob
from chat_nexus_mod_manager.models.settings import AppSetting
from chat_nexus_mod_manager.routers.deps import get_game_or_404
from chat_nexus_mod_manager.services.update_service import (
    check_all_updates,
    check_cached_updates,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/updates", tags=["updates"])


class ModUpdate(BaseModel):
    mod_group_id: int | None = None
    display_name: str
    local_version: str
    nexus_version: str
    nexus_mod_id: int
    nexus_file_id: int | None = None
    nexus_file_name: str = ""
    nexus_url: str
    author: str
    installed_mod_id: int | None = None
    source: str = "correlation"
    local_timestamp: int | None = None
    nexus_timestamp: int | None = None
    detection_method: Literal["timestamp", "version", "both"] = "version"
    source_archive: str | None = None
    reason: str = ""
    local_download_date: int | None = None


class UpdateCheckResult(BaseModel):
    total_checked: int
    updates_available: int
    updates: list[ModUpdate]


def _enrich_download_dates(
    updates: list[ModUpdate], session: Session, game_id: int, install_path: str
) -> None:
    """Populate local_download_date from DownloadJob or archive file mtime."""
    archives = {u.source_archive for u in updates if u.source_archive}
    if not archives:
        return

    # DownloadJob completed_at
    dl_rows = session.exec(
        select(DownloadJob.file_name, DownloadJob.completed_at).where(
            DownloadJob.game_id == game_id,
            DownloadJob.status == "completed",
            DownloadJob.completed_at.is_not(None),  # type: ignore[union-attr]
            DownloadJob.file_name.in_(archives),  # type: ignore[union-attr]
        )
    ).all()
    dl_map: dict[str, int] = {}
    for fn, completed in dl_rows:
        if fn and completed:
            if completed.tzinfo is None:
                ts = int(completed.replace(tzinfo=UTC).timestamp())
            else:
                ts = int(completed.timestamp())
            existing = dl_map.get(fn)
            if existing is None or ts > existing:
                dl_map[fn] = ts

    # Archive file mtime fallback
    staging = Path(install_path) / "downloaded_mods"
    for fn in archives - dl_map.keys():
        try:
            dl_map[fn] = int(os.stat(staging / fn).st_mtime)
        except OSError:
            continue

    for u in updates:
        if u.source_archive:
            u.local_download_date = dl_map.get(u.source_archive)


@router.get("/", response_model=UpdateCheckResult)
def list_updates(game_name: str, session: Session = Depends(get_session)) -> UpdateCheckResult:
    """Return cached update info (no API calls, uses last-refreshed metadata)."""
    game = get_game_or_404(game_name, session)
    result = check_cached_updates(game.id, game.domain_name, session)  # type: ignore[arg-type]
    updates = [ModUpdate(**u) for u in result.updates]
    _enrich_download_dates(updates, session, game.id, game.install_path)  # type: ignore[arg-type]
    return UpdateCheckResult(
        total_checked=result.total_checked,
        updates_available=len(updates),
        updates=updates,
    )


@router.post("/check", response_model=UpdateCheckResult)
async def check_updates(
    game_name: str, session: Session = Depends(get_session)
) -> UpdateCheckResult:
    """Unified update check across installed, correlated, endorsed, and tracked mods.

    Refreshes Nexus metadata for recently updated mods, then compares versions.
    """
    game = get_game_or_404(game_name, session)

    key_setting = session.exec(select(AppSetting).where(AppSetting.key == "nexus_api_key")).first()
    has_key = bool(key_setting and key_setting.value)

    if has_key:
        from chat_nexus_mod_manager.nexus.client import NexusClient

        async with NexusClient(key_setting.value) as client:  # type: ignore[union-attr]
            result = await check_all_updates(
                game.id,  # type: ignore[arg-type]
                game.domain_name,
                client,
                session,  # type: ignore[arg-type]
                install_path=game.install_path,
            )
    else:
        result = check_cached_updates(game.id, game.domain_name, session)  # type: ignore[arg-type]

    updates = [ModUpdate(**u) for u in result.updates]
    _enrich_download_dates(updates, session, game.id, game.install_path)  # type: ignore[arg-type]
    return UpdateCheckResult(
        total_checked=result.total_checked,
        updates_available=len(updates),
        updates=updates,
    )
