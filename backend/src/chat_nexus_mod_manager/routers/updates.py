import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.nexus import NexusModMeta
from chat_nexus_mod_manager.models.settings import AppSetting
from chat_nexus_mod_manager.routers.deps import get_game_or_404
from chat_nexus_mod_manager.services.update_service import (
    check_correlation_updates,
    check_installed_mod_updates,
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
    game = get_game_or_404(game_name, session)

    key_setting = session.exec(select(AppSetting).where(AppSetting.key == "nexus_api_key")).first()

    installed_total = 0
    installed_updates: list[dict] = []
    covered_nexus_ids: set[int] = set()

    if key_setting and key_setting.value:
        from chat_nexus_mod_manager.nexus.client import NexusClient

        async with NexusClient(key_setting.value) as client:
            # Refresh NexusModMeta from recently updated mods (best-effort)
            try:
                updated_mods = await client.get_updated_mods(game.domain_name, "1w")
                for mod_data in updated_mods:
                    nexus_mod_id = mod_data.get("mod_id")
                    if nexus_mod_id:
                        meta = session.exec(
                            select(NexusModMeta).where(NexusModMeta.nexus_mod_id == nexus_mod_id)
                        ).first()
                        if meta:
                            latest = mod_data.get("latest_file_update") or mod_data.get(
                                "latest_mod_activity"
                            )
                            if latest:
                                info = await client.get_mod_info(game.domain_name, nexus_mod_id)
                                if info:
                                    meta.version = info.get("version", meta.version)
                                    ts = info.get("updated_timestamp")
                                    if ts:
                                        meta.updated_at = datetime.fromtimestamp(ts, tz=UTC)
                                session.add(meta)
                session.commit()
            except (httpx.HTTPError, ValueError):
                logger.warning("Failed to refresh mod metadata", exc_info=True)

            # Timestamp-based update checking for installed mods
            installed_result = await check_installed_mod_updates(
                game.id,
                game.domain_name,
                client,
                session,  # type: ignore[arg-type]
            )
            installed_total = installed_result.total_checked
            installed_updates = installed_result.updates
            covered_nexus_ids = {u["nexus_mod_id"] for u in installed_updates}

    # Correlation-based updates for mods not covered by installed path
    correlation_result = check_correlation_updates(game.id, session)  # type: ignore[arg-type]
    filtered_correlation = [
        u for u in correlation_result.updates if u["nexus_mod_id"] not in covered_nexus_ids
    ]

    all_updates_raw = installed_updates + filtered_correlation
    all_updates = [ModUpdate(**u) for u in all_updates_raw]
    total = installed_total + correlation_result.total_checked

    return UpdateCheckResult(
        total_checked=total,
        updates_available=len(all_updates),
        updates=all_updates,
    )
