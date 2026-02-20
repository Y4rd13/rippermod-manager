from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.settings import AppSetting
from chat_nexus_mod_manager.routers.deps import get_game_or_404
from chat_nexus_mod_manager.services.update_service import (
    check_all_updates,
    check_correlation_updates,
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


class UpdateCheckResult(BaseModel):
    total_checked: int
    updates_available: int
    updates: list[ModUpdate]


@router.get("/", response_model=UpdateCheckResult)
def list_updates(game_name: str, session: Session = Depends(get_session)) -> UpdateCheckResult:
    """Return cached update info (no API calls, uses last-refreshed metadata)."""
    game = get_game_or_404(game_name, session)
    result = check_correlation_updates(game.id, session)  # type: ignore[arg-type]
    updates = [ModUpdate(**u) for u in result.updates]
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
            )
    else:
        result = check_correlation_updates(game.id, session)  # type: ignore[arg-type]

    updates = [ModUpdate(**u) for u in result.updates]
    return UpdateCheckResult(
        total_checked=result.total_checked,
        updates_available=len(updates),
        updates=updates,
    )
