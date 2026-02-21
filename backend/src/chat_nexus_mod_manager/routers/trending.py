"""Router for trending (latest updated) mods from Nexus."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.nexus.client import NexusClient, NexusRateLimitError
from chat_nexus_mod_manager.routers.deps import get_game_or_404
from chat_nexus_mod_manager.schemas.nexus import TrendingResult
from chat_nexus_mod_manager.services.settings_helpers import get_setting
from chat_nexus_mod_manager.services.trending_service import (
    fetch_trending_mods,
    get_cached_trending,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/trending", tags=["trending"])


@router.get("/", response_model=TrendingResult)
async def get_trending(
    game_name: str,
    refresh: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> TrendingResult:
    game = get_game_or_404(game_name, session)
    api_key = get_setting(session, "nexus_api_key")
    if not api_key:
        raise HTTPException(400, "Nexus API key not configured")

    try:
        async with NexusClient(api_key) as client:
            return await fetch_trending_mods(
                game.id,  # type: ignore[arg-type]
                game.domain_name,
                client,
                session,
                force_refresh=refresh,
            )
    except (httpx.HTTPError, NexusRateLimitError) as exc:
        logger.exception("Failed to fetch trending mods from Nexus API")
        cached = get_cached_trending(game.id, game.domain_name, session)  # type: ignore[arg-type]
        if cached is not None:
            return cached
        raise HTTPException(502, "Failed to fetch trending mods and no cache available") from exc
