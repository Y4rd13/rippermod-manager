from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from chat_nexus_mod_manager.nexus.client import NexusClient

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
    has_key = bool(key_setting and key_setting.value)

    installed_total = 0
    installed_updates: list[dict] = []
    covered_nexus_ids: set[int] = set()
    filtered_correlation: list[dict] = []
    correlation_total = 0

    if has_key:
        from chat_nexus_mod_manager.nexus.client import NexusClient

        async with NexusClient(key_setting.value) as client:  # type: ignore[union-attr]
            # Refresh NexusModMeta from recently updated mods (best-effort)
            try:
                updated_mods = await client.get_updated_mods(game.domain_name, "1m")
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
                            # Skip if metadata is already up-to-date
                            if latest and meta.updated_at:
                                latest_dt = datetime.fromtimestamp(latest, tz=UTC)
                                if meta.updated_at >= latest_dt:
                                    continue
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
            correlation_result = check_correlation_updates(
                game.id,
                session,  # type: ignore[arg-type]
            )
            correlation_total = correlation_result.total_checked
            filtered_correlation = [
                u for u in correlation_result.updates if u["nexus_mod_id"] not in covered_nexus_ids
            ]

            # Resolve nexus_file_id for correlation updates (enables Download button)
            if filtered_correlation:
                await _resolve_file_ids(client, game.domain_name, filtered_correlation)
    else:
        # No API key — correlation-only (no file resolution possible)
        correlation_result = check_correlation_updates(
            game.id,
            session,  # type: ignore[arg-type]
        )
        correlation_total = correlation_result.total_checked
        filtered_correlation = correlation_result.updates

    all_updates_raw = installed_updates + filtered_correlation
    all_updates = [ModUpdate(**u) for u in all_updates_raw]
    total = installed_total + correlation_total

    return UpdateCheckResult(
        total_checked=total,
        updates_available=len(all_updates),
        updates=all_updates,
    )


async def _resolve_file_ids(
    client: NexusClient,
    game_domain: str,
    updates: list[dict],
) -> None:
    """Resolve the best nexus_file_id for correlation updates lacking one."""
    sem = asyncio.Semaphore(5)

    async def _resolve_one(update_dict: dict) -> None:
        if update_dict.get("nexus_file_id"):
            return
        async with sem:
            try:
                files_resp = await client.get_mod_files(game_domain, update_dict["nexus_mod_id"])
                nexus_files = files_resp.get("files", [])
                # Pick the most recent MAIN file (category_id == 1)
                main_files = [f for f in nexus_files if f.get("category_id") == 1]
                if main_files:
                    best = max(main_files, key=lambda f: f.get("uploaded_timestamp", 0))
                else:
                    active = [f for f in nexus_files if f.get("category_id") != 7]
                    best = (
                        max(active, key=lambda f: f.get("uploaded_timestamp", 0))
                        if active
                        else None
                    )
                if best:
                    update_dict["nexus_file_id"] = best.get("file_id")
                    update_dict["nexus_file_name"] = best.get("file_name", "")
                    update_dict["nexus_version"] = best.get("version", update_dict["nexus_version"])
                    update_dict["nexus_timestamp"] = best.get("uploaded_timestamp")
            except Exception:
                logger.warning(
                    "Failed to resolve file for mod %d",
                    update_dict["nexus_mod_id"],
                    exc_info=True,
                )

    await asyncio.gather(*(_resolve_one(u) for u in updates))
