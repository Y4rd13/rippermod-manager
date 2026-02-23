"""Service for fetching and caching trending and latest updated mods from Nexus."""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusDownload, NexusModMeta
from rippermod_manager.nexus.client import NexusClient
from rippermod_manager.schemas.nexus import TrendingModOut, TrendingResult
from rippermod_manager.services.settings_helpers import get_setting, set_setting

logger = logging.getLogger(__name__)

_CACHE_TTL = 15 * 60  # 15 minutes


def _load_cached(prefix: str, game_id: int, session: Session) -> list[dict[str, Any]] | None:
    ts_raw = get_setting(session, f"{prefix}_ts_{game_id}")
    if not ts_raw:
        return None
    try:
        cached_at = float(ts_raw)
    except ValueError:
        return None
    if time.time() - cached_at > _CACHE_TTL:
        return None
    raw = get_setting(session, f"{prefix}_{game_id}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _save_cached(
    prefix: str, game_id: int, mods_data: list[dict[str, Any]], session: Session
) -> None:
    set_setting(session, f"{prefix}_{game_id}", json.dumps(mods_data))
    set_setting(session, f"{prefix}_ts_{game_id}", str(time.time()))


def _upsert_trending_metadata(
    mods_data: list[dict[str, Any]], game_domain: str, session: Session
) -> None:
    for info in mods_data:
        mod_id = info.get("mod_id", 0)
        if not mod_id:
            continue
        existing = session.exec(
            select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)
        ).first()
        name = info.get("name", "")
        version = info.get("version", "")
        if not existing:
            meta = NexusModMeta(
                nexus_mod_id=mod_id,
                game_domain=game_domain,
                name=name,
                summary=info.get("summary", ""),
                author=info.get("author", ""),
                version=version,
                endorsement_count=info.get("endorsement_count", 0),
                category=str(info.get("category_id", "")),
                picture_url=info.get("picture_url", ""),
            )
            created_ts = info.get("created_timestamp")
            if created_ts:
                meta.created_at = datetime.fromtimestamp(created_ts, tz=UTC)
            ts = info.get("updated_timestamp")
            if ts:
                meta.updated_at = datetime.fromtimestamp(ts, tz=UTC)
            session.add(meta)
        else:
            if name:
                existing.name = name
            if info.get("summary"):
                existing.summary = info["summary"]
            if version:
                existing.version = version
            if info.get("author"):
                existing.author = info["author"]
            if info.get("endorsement_count") is not None:
                existing.endorsement_count = info["endorsement_count"]
            if info.get("picture_url"):
                existing.picture_url = info["picture_url"]
            created_ts = info.get("created_timestamp")
            if created_ts:
                existing.created_at = datetime.fromtimestamp(created_ts, tz=UTC)
            ts = info.get("updated_timestamp")
            if ts:
                existing.updated_at = datetime.fromtimestamp(ts, tz=UTC)


def _normalize_api_response(raw_mods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Nexus API response to our internal format."""
    result = []
    for m in raw_mods:
        result.append(
            {
                "mod_id": m.get("mod_id", 0),
                "name": m.get("name", ""),
                "summary": m.get("summary", ""),
                "author": m.get("author", ""),
                "version": m.get("version", ""),
                "picture_url": m.get("picture_url", ""),
                "endorsement_count": m.get("endorsement_count", 0),
                "mod_downloads": m.get("mod_downloads", 0),
                "mod_unique_downloads": m.get("mod_unique_downloads", 0),
                "created_timestamp": m.get("created_timestamp", 0),
                "updated_timestamp": m.get("updated_timestamp", 0),
                "category_id": m.get("category_id"),
            }
        )
    return result


def _cross_reference(
    mods_data: list[dict[str, Any]],
    game_id: int,
    game_domain: str,
    session: Session,
) -> list[TrendingModOut]:
    mod_ids = [m["mod_id"] for m in mods_data if m.get("mod_id")]

    installed_nexus_ids: set[int] = set()
    if mod_ids:
        rows = session.exec(
            select(InstalledMod.nexus_mod_id).where(
                InstalledMod.game_id == game_id,
                InstalledMod.nexus_mod_id.in_(mod_ids),  # type: ignore[union-attr]
            )
        ).all()
        installed_nexus_ids = {r for r in rows if r is not None}

    tracked_ids: set[int] = set()
    endorsed_ids: set[int] = set()
    if mod_ids:
        dl_rows = session.exec(
            select(
                NexusDownload.nexus_mod_id,
                NexusDownload.is_tracked,
                NexusDownload.is_endorsed,
            ).where(
                NexusDownload.game_id == game_id,
                NexusDownload.nexus_mod_id.in_(mod_ids),  # type: ignore[union-attr]
            )
        ).all()
        for nexus_mod_id, is_tracked, is_endorsed in dl_rows:
            if is_tracked:
                tracked_ids.add(nexus_mod_id)
            if is_endorsed:
                endorsed_ids.add(nexus_mod_id)

    nexus_url_base = f"https://www.nexusmods.com/{game_domain}/mods"
    result = []
    for m in mods_data:
        mid = m["mod_id"]
        result.append(
            TrendingModOut(
                mod_id=mid,
                name=m.get("name", ""),
                summary=m.get("summary", ""),
                author=m.get("author", ""),
                version=m.get("version", ""),
                picture_url=m.get("picture_url", ""),
                endorsement_count=m.get("endorsement_count", 0),
                mod_downloads=m.get("mod_downloads", 0),
                mod_unique_downloads=m.get("mod_unique_downloads", 0),
                created_timestamp=m.get("created_timestamp", 0),
                updated_timestamp=m.get("updated_timestamp", 0),
                category_id=m.get("category_id"),
                nexus_url=f"{nexus_url_base}/{mid}",
                is_installed=mid in installed_nexus_ids,
                is_tracked=mid in tracked_ids,
                is_endorsed=mid in endorsed_ids,
            )
        )
    return result


async def fetch_trending_mods(
    game_id: int,
    game_domain: str,
    client: NexusClient,
    session: Session,
    *,
    force_refresh: bool = False,
) -> TrendingResult:
    if not force_refresh:
        cached_trending = _load_cached("trending_cache", game_id, session)
        cached_latest = _load_cached("latest_updated_cache", game_id, session)
        if cached_trending is not None and cached_latest is not None:
            trending = _cross_reference(cached_trending, game_id, game_domain, session)
            latest = _cross_reference(cached_latest, game_id, game_domain, session)
            return TrendingResult(trending=trending, latest_updated=latest, cached=True)

    raw_trending, raw_latest = await asyncio.gather(
        client.get_trending(game_domain),
        client.get_latest_updated(game_domain),
    )

    normalized_trending = _normalize_api_response(raw_trending)
    normalized_latest = _normalize_api_response(raw_latest)

    all_mods = {m["mod_id"]: m for m in normalized_trending + normalized_latest}
    _upsert_trending_metadata(list(all_mods.values()), game_domain, session)

    _save_cached("trending_cache", game_id, normalized_trending, session)
    _save_cached("latest_updated_cache", game_id, normalized_latest, session)
    session.commit()

    trending = _cross_reference(normalized_trending, game_id, game_domain, session)
    latest = _cross_reference(normalized_latest, game_id, game_domain, session)
    return TrendingResult(trending=trending, latest_updated=latest, cached=False)


def get_cached_trending(game_id: int, game_domain: str, session: Session) -> TrendingResult | None:
    """Serve stale cache (ignore TTL) for error-fallback paths."""
    raw_trending = get_setting(session, f"trending_cache_{game_id}")
    raw_latest = get_setting(session, f"latest_updated_cache_{game_id}")
    if not raw_trending and not raw_latest:
        return None
    try:
        trending_data = json.loads(raw_trending) if raw_trending else []
        latest_data = json.loads(raw_latest) if raw_latest else []
    except json.JSONDecodeError:
        return None
    trending = _cross_reference(trending_data, game_id, game_domain, session)
    latest = _cross_reference(latest_data, game_id, game_domain, session)
    return TrendingResult(trending=trending, latest_updated=latest, cached=True)
