"""Unified update checking across installed, correlated, endorsed, and tracked mods.

Strategy (optimal API usage):
1. Collect ALL nexus_mod_ids from every source with local version info
2. Deduplicate: installed > correlation > endorsed > tracked
3. Fetch recently updated mods (1 API call: get_updated_mods("1m"))
4. Refresh NexusModMeta only for mods that changed on Nexus
5. Compare local versions against NexusModMeta via is_newer_version()
6. Resolve file IDs only for mods with confirmed updates
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlmodel import Session, select

from chat_nexus_mod_manager.matching.filename_parser import (
    is_newer_version,
    parse_mod_filename,
)
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.nexus.client import NexusClient

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 5


@dataclass(frozen=True, slots=True)
class TrackedMod:
    """A mod we track for updates, from any source."""

    nexus_mod_id: int
    local_version: str
    display_name: str
    source: str  # "installed", "correlation", "endorsed", "tracked"
    installed_mod_id: int | None = None
    mod_group_id: int | None = None
    upload_timestamp: int | None = None
    nexus_url: str = ""


@dataclass
class UpdateResult:
    total_checked: int = 0
    updates: list[dict[str, Any]] = field(default_factory=list)


def collect_tracked_mods(game_id: int, game_domain: str, session: Session) -> dict[int, TrackedMod]:
    """Collect all nexus_mod_ids with local versions, deduplicated by priority.

    Priority: installed > correlation > endorsed/tracked.
    Returns a dict keyed by nexus_mod_id.
    """
    mods: dict[int, TrackedMod] = {}

    # Source 1: Installed mods (highest priority)
    installed = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game_id,
            InstalledMod.nexus_mod_id.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    for mod in installed:
        mid = mod.nexus_mod_id
        if not mid or not mod.installed_version:
            continue
        nexus_url = f"https://www.nexusmods.com/{game_domain}/mods/{mid}"
        mods[mid] = TrackedMod(
            nexus_mod_id=mid,
            local_version=mod.installed_version,
            display_name=mod.name,
            source="installed",
            installed_mod_id=mod.id,
            mod_group_id=mod.mod_group_id,
            upload_timestamp=mod.upload_timestamp,
            nexus_url=nexus_url,
        )

    # Source 2: Correlated mods (Nexus Matched)
    correlations = session.exec(
        select(ModNexusCorrelation, ModGroup, NexusDownload)
        .join(ModGroup, ModNexusCorrelation.mod_group_id == ModGroup.id)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .where(ModGroup.game_id == game_id)
    ).all()
    for _corr, group, dl in correlations:
        mid = dl.nexus_mod_id
        if mid in mods:
            continue
        parsed = parse_mod_filename(dl.file_name) if dl.file_name else None
        local_v = (parsed.version if parsed and parsed.version else None) or dl.version
        if not local_v:
            continue
        mods[mid] = TrackedMod(
            nexus_mod_id=mid,
            local_version=local_v,
            display_name=group.display_name,
            source="correlation",
            mod_group_id=group.id,
            nexus_url=dl.nexus_url,
        )

    # Source 3: Endorsed and tracked mods
    nexus_dls = session.exec(
        select(NexusDownload).where(
            NexusDownload.game_id == game_id,
            (NexusDownload.is_endorsed.is_(True)) | (NexusDownload.is_tracked.is_(True)),
        )
    ).all()
    for dl in nexus_dls:
        mid = dl.nexus_mod_id
        if mid in mods:
            continue
        if not dl.version:
            continue
        source = "endorsed" if dl.is_endorsed else "tracked"
        mods[mid] = TrackedMod(
            nexus_mod_id=mid,
            local_version=dl.version,
            display_name=dl.mod_name,
            source=source,
            nexus_url=dl.nexus_url,
        )

    return mods


async def _refresh_metadata(
    client: NexusClient,
    game_domain: str,
    mod_ids: set[int],
    session: Session,
) -> None:
    """Refresh NexusModMeta for a set of mod IDs via concurrent get_mod_info calls."""
    if not mod_ids:
        return

    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def refresh_one(mod_id: int) -> None:
        async with sem:
            try:
                info = await client.get_mod_info(game_domain, mod_id)
            except (httpx.HTTPError, ValueError):
                logger.warning("Failed to refresh metadata for mod %d", mod_id)
                return
            meta = session.exec(
                select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)
            ).first()
            if meta:
                meta.version = info.get("version", meta.version)
                ts = info.get("updated_timestamp")
                if ts:
                    meta.updated_at = datetime.fromtimestamp(ts, tz=UTC)
                session.add(meta)

    await asyncio.gather(*(refresh_one(mid) for mid in mod_ids))
    session.commit()


async def _resolve_file_ids(
    client: NexusClient,
    game_domain: str,
    updates: list[dict[str, Any]],
) -> None:
    """Resolve nexus_file_id for updates that lack one."""
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def resolve_one(update: dict[str, Any]) -> None:
        if update.get("nexus_file_id"):
            return
        async with sem:
            try:
                files_resp = await client.get_mod_files(game_domain, update["nexus_mod_id"])
                nexus_files = files_resp.get("files", [])
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
                    update["nexus_file_id"] = best.get("file_id")
                    update["nexus_file_name"] = best.get("file_name", "")
                    update["nexus_version"] = best.get("version", update["nexus_version"])
                    update["nexus_timestamp"] = best.get("uploaded_timestamp")
            except Exception:
                logger.warning(
                    "Failed to resolve file for mod %d",
                    update["nexus_mod_id"],
                    exc_info=True,
                )

    await asyncio.gather(*(resolve_one(u) for u in updates))


async def check_all_updates(
    game_id: int,
    game_domain: str,
    client: NexusClient,
    session: Session,
) -> UpdateResult:
    """Unified update check across all mod sources.

    1. Collect tracked mods from installed, correlated, endorsed, and tracked
    2. Fetch recently updated mods from Nexus (1 API call)
    3. Refresh metadata only for mods that actually changed
    4. Compare versions for all tracked mods
    5. Resolve file IDs for updates
    """
    tracked = collect_tracked_mods(game_id, game_domain, session)
    if not tracked:
        return UpdateResult()

    logger.info("Update check: %d unique mods from all sources", len(tracked))

    # 1 API call: get all mods updated in last month
    try:
        updated_entries = await client.get_updated_mods(game_domain, "1m")
        recently_updated_ids = {e["mod_id"] for e in updated_entries}
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to fetch recently updated mods", exc_info=True)
        recently_updated_ids = set()

    # Refresh metadata only for mods in our set that were recently updated on Nexus
    to_refresh = recently_updated_ids & set(tracked.keys())
    if to_refresh:
        logger.info("Refreshing metadata for %d recently updated mods", len(to_refresh))
        await _refresh_metadata(client, game_domain, to_refresh, session)

    # Load all NexusModMeta for our tracked mods
    tracked_ids = list(tracked.keys())
    meta_rows = session.exec(
        select(NexusModMeta).where(
            NexusModMeta.nexus_mod_id.in_(tracked_ids)  # type: ignore[union-attr]
        )
    ).all()
    meta_map = {m.nexus_mod_id: m for m in meta_rows}

    # Compare versions
    updates: list[dict[str, Any]] = []
    for mid, mod in tracked.items():
        meta = meta_map.get(mid)
        if not meta or not meta.version:
            logger.debug("Skip mod %d (%s): no metadata version", mid, mod.display_name)
            continue

        if is_newer_version(meta.version, mod.local_version):
            logger.debug(
                "UPDATE %s: local=%s, nexus=%s (source=%s)",
                mod.display_name,
                mod.local_version,
                meta.version,
                mod.source,
            )
            updates.append(
                {
                    "installed_mod_id": mod.installed_mod_id,
                    "mod_group_id": mod.mod_group_id,
                    "display_name": mod.display_name,
                    "local_version": mod.local_version,
                    "nexus_version": meta.version,
                    "nexus_mod_id": mid,
                    "nexus_file_id": None,
                    "nexus_file_name": "",
                    "nexus_url": mod.nexus_url
                    or f"https://www.nexusmods.com/{game_domain}/mods/{mid}",
                    "author": meta.author,
                    "source": mod.source,
                    "local_timestamp": mod.upload_timestamp,
                    "nexus_timestamp": None,
                }
            )
        else:
            logger.debug(
                "OK %s: local=%s, nexus=%s",
                mod.display_name,
                mod.local_version,
                meta.version,
            )

    # Resolve file IDs for downloads
    if updates:
        await _resolve_file_ids(client, game_domain, updates)

    logger.info("Update check complete: %d updates from %d mods", len(updates), len(tracked))
    return UpdateResult(total_checked=len(tracked), updates=updates)


def check_correlation_updates(
    game_id: int,
    session: Session,
) -> UpdateResult:
    """Lightweight correlation-only check (no API calls, for GET endpoint).

    Compares NexusDownload.version (frozen) against NexusModMeta.version (refreshed).
    """
    tracked = collect_tracked_mods(game_id, "", session)
    if not tracked:
        return UpdateResult()

    tracked_ids = list(tracked.keys())
    meta_rows = session.exec(
        select(NexusModMeta).where(
            NexusModMeta.nexus_mod_id.in_(tracked_ids)  # type: ignore[union-attr]
        )
    ).all()
    meta_map = {m.nexus_mod_id: m for m in meta_rows}

    updates: list[dict[str, Any]] = []
    for mid, mod in tracked.items():
        meta = meta_map.get(mid)
        if not meta or not meta.version:
            continue
        if is_newer_version(meta.version, mod.local_version):
            updates.append(
                {
                    "installed_mod_id": mod.installed_mod_id,
                    "mod_group_id": mod.mod_group_id,
                    "display_name": mod.display_name,
                    "local_version": mod.local_version,
                    "nexus_version": meta.version,
                    "nexus_mod_id": mid,
                    "nexus_file_id": None,
                    "nexus_file_name": "",
                    "nexus_url": mod.nexus_url
                    or f"https://www.nexusmods.com/{meta.game_domain}/mods/{mid}",
                    "author": meta.author,
                    "source": mod.source,
                    "local_timestamp": mod.upload_timestamp,
                    "nexus_timestamp": None,
                }
            )

    return UpdateResult(total_checked=len(tracked), updates=updates)
