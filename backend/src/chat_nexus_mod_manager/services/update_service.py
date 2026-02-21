"""Unified update checking across installed, correlated, endorsed, and tracked mods.

Strategy (optimal API usage):
1. Collect ALL nexus_mod_ids from every source with local version info
2. Deduplicate: installed > correlation > endorsed > tracked
3. Fetch recently updated mods (1 API call: get_updated_mods("1m"))
4. Compare latest_file_update timestamps against NexusModMeta.updated_at
5. Refresh NexusModMeta only for mods flagged by timestamp comparison
6. Build updates from BOTH timestamp flags and version comparison
7. Resolve file IDs only for mods with confirmed updates
8. Cache results in AppSetting for the GET endpoint
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
from chat_nexus_mod_manager.services.nexus_helpers import match_local_to_nexus_file
from chat_nexus_mod_manager.services.settings_helpers import get_setting, set_setting

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 5
_CACHE_KEY_PREFIX = "update_cache_"
_CACHE_TTL = timedelta(hours=24)


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
    source_archive: str = ""


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
            source_archive=mod.source_archive,
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
            source_archive=dl.file_name,
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
            source_archive=dl.file_name,
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
            else:
                new_meta = NexusModMeta(
                    nexus_mod_id=mod_id,
                    game_domain=game_domain,
                    name=info.get("name", ""),
                    version=info.get("version", ""),
                    author=info.get("author", ""),
                    summary=info.get("summary", ""),
                    endorsement_count=info.get("endorsement_count", 0),
                    picture_url=info.get("picture_url", ""),
                )
                ts = info.get("updated_timestamp")
                if ts:
                    new_meta.updated_at = datetime.fromtimestamp(ts, tz=UTC)
                session.add(new_meta)

    await asyncio.gather(*(refresh_one(mid) for mid in mod_ids))
    session.commit()


async def _resolve_file_ids(
    client: NexusClient,
    game_domain: str,
    updates: list[dict[str, Any]],
) -> None:
    """Resolve nexus_file_id for updates that lack one.

    Uses ``match_local_to_nexus_file()`` when a local filename is available,
    then checks ``file_updates`` chains for direct replacement info.
    """
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def resolve_one(update: dict[str, Any]) -> None:
        if update.get("nexus_file_id"):
            return
        async with sem:
            try:
                files_resp = await client.get_mod_files(game_domain, update["nexus_mod_id"])
                nexus_files = files_resp.get("files", [])
                file_updates = files_resp.get("file_updates", [])

                local_fn = update.get("local_filename", "")
                best: dict[str, Any] | None = None

                if local_fn:
                    parsed = parse_mod_filename(local_fn)
                    best = match_local_to_nexus_file(
                        local_fn,
                        nexus_files,
                        parsed_version=parsed.version,
                        parsed_timestamp=parsed.upload_timestamp,
                    )

                    # Save the originally-matched file_id (what's installed locally)
                    # for persistence, before following the update chain.
                    if best:
                        update["_matched_file_id"] = best.get("file_id")

                    # Check file_updates chain: if matched file appears as old_file_id,
                    # follow the chain to the newest replacement (download target)
                    if best and file_updates:
                        matched_fid = best.get("file_id")
                        chain: dict[int, int] = {
                            fu["old_file_id"]: fu["new_file_id"]
                            for fu in file_updates
                            if "old_file_id" in fu and "new_file_id" in fu
                        }
                        visited: set[int] = set()
                        current = matched_fid
                        while current in chain and current not in visited:
                            visited.add(current)
                            current = chain[current]
                        if current and current != matched_fid:
                            new_file = next(
                                (f for f in nexus_files if f.get("file_id") == current), None
                            )
                            if new_file and new_file.get("category_id") != 7:
                                best = new_file

                if not best:
                    # No local filename — fall back to most recent MAIN file
                    best = match_local_to_nexus_file("", nexus_files)

                if best:
                    update["nexus_file_id"] = best.get("file_id")
                    update["nexus_file_name"] = best.get("file_name", "")
                    update["nexus_version"] = best.get("version", update["nexus_version"])
                    update["nexus_timestamp"] = best.get("uploaded_timestamp")
            except (httpx.HTTPError, ValueError, KeyError):
                logger.warning(
                    "Failed to resolve file for mod %d",
                    update["nexus_mod_id"],
                    exc_info=True,
                )

    await asyncio.gather(*(resolve_one(u) for u in updates))


def _persist_resolved_file_ids(
    updates: list[dict[str, Any]],
    session: Session,
    game_id: int,
) -> None:
    """Persist resolved nexus_file_ids back to InstalledMod and NexusDownload.

    For InstalledMod, uses the pre-chain ``_matched_file_id`` (the file that
    corresponds to what's actually installed), not the chain-followed download
    target in ``nexus_file_id``.
    """
    for update in updates:
        fid = update.get("nexus_file_id")
        if not fid:
            continue

        mid = update["nexus_mod_id"]

        # Use pre-chain file_id for InstalledMod (what's actually installed)
        installed_fid = update.get("_matched_file_id") or fid
        installed_id = update.get("installed_mod_id")
        if installed_id:
            installed = session.get(InstalledMod, installed_id)
            if installed and not installed.nexus_file_id:
                installed.nexus_file_id = installed_fid
                session.add(installed)

        # Use pre-chain file_id for NexusDownload (represents discovery-time file)
        dl_fid = update.get("_matched_file_id") or fid
        nx_dl = session.exec(
            select(NexusDownload).where(
                NexusDownload.game_id == game_id,
                NexusDownload.nexus_mod_id == mid,
            )
        ).first()
        if nx_dl and not nx_dl.file_id:
            nx_dl.file_id = dl_fid
            session.add(nx_dl)

    session.commit()


def _cache_update_result(game_id: int, result: UpdateResult, session: Session) -> None:
    """Serialize and persist update result to AppSetting."""
    payload = {
        "total_checked": result.total_checked,
        "updates": result.updates,
        "cached_at": datetime.now(UTC).isoformat(),
    }
    set_setting(session, f"{_CACHE_KEY_PREFIX}{game_id}", json.dumps(payload))
    session.commit()


def _load_cached_result(game_id: int, session: Session) -> UpdateResult | None:
    """Load a previously cached update result from AppSetting, respecting TTL."""
    raw = get_setting(session, f"{_CACHE_KEY_PREFIX}{game_id}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        cached_at = datetime.fromisoformat(data.get("cached_at", ""))
        if datetime.now(UTC) - cached_at > _CACHE_TTL:
            return None
        return UpdateResult(
            total_checked=data["total_checked"],
            updates=data["updates"],
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("Failed to parse cached update result for game %d", game_id)
        return None


async def check_all_updates(
    game_id: int,
    game_domain: str,
    client: NexusClient,
    session: Session,
) -> UpdateResult:
    """Unified update check across all mod sources.

    1. Collect tracked mods from installed, correlated, endorsed, and tracked
    2. Fetch recently updated mods from Nexus (1 API call)
    3. Build file_update_map and compare against NexusModMeta.updated_at
    4. Refresh metadata only for mods flagged by timestamp
    5. Compare versions for all tracked mods (catches both paths)
    6. Resolve file IDs for updates
    7. Cache result for the GET endpoint
    """
    tracked = collect_tracked_mods(game_id, game_domain, session)
    if not tracked:
        return UpdateResult()

    logger.info("Update check: %d unique mods from all sources", len(tracked))

    # 1 API call: get all mods updated in last month
    file_update_map: dict[int, int] = {}
    try:
        updated_entries = await client.get_updated_mods(game_domain, "1m")
        for entry in updated_entries:
            file_update_map[entry["mod_id"]] = entry.get("latest_file_update", 0)
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to fetch recently updated mods", exc_info=True)

    # Load pre-refresh updated_at baselines for our tracked mods
    tracked_ids = list(tracked.keys())
    meta_rows = session.exec(
        select(NexusModMeta).where(
            NexusModMeta.nexus_mod_id.in_(tracked_ids)  # type: ignore[union-attr]
        )
    ).all()
    baseline_map: dict[int, datetime | None] = {m.nexus_mod_id: m.updated_at for m in meta_rows}

    # Flag mods where latest_file_update > updated_at (or updated_at is NULL)
    timestamp_flagged: set[int] = set()
    for mid in tracked:
        latest_file_ts = file_update_map.get(mid)
        if latest_file_ts is None:
            continue
        baseline = baseline_map.get(mid)
        if baseline is None:
            timestamp_flagged.add(mid)
        else:
            # SQLite drops tzinfo; treat naive datetimes as UTC
            baseline_utc = baseline.replace(tzinfo=UTC) if baseline.tzinfo is None else baseline
            baseline_epoch = int(baseline_utc.timestamp())
            if latest_file_ts > baseline_epoch:
                timestamp_flagged.add(mid)

    # Refresh metadata only for flagged mods
    if timestamp_flagged:
        logger.info("Refreshing metadata for %d timestamp-flagged mods", len(timestamp_flagged))
        await _refresh_metadata(client, game_domain, timestamp_flagged, session)

    # Reload metadata after refresh
    meta_rows = session.exec(
        select(NexusModMeta).where(
            NexusModMeta.nexus_mod_id.in_(tracked_ids)  # type: ignore[union-attr]
        )
    ).all()
    meta_map = {m.nexus_mod_id: m for m in meta_rows}

    # Build updates from BOTH: timestamp flags OR version comparison
    updates: list[dict[str, Any]] = []
    for mid, mod in tracked.items():
        meta = meta_map.get(mid)
        if not meta or not meta.version:
            logger.debug("Skip mod %d (%s): no metadata version", mid, mod.display_name)
            continue

        is_timestamp_flagged = mid in timestamp_flagged
        is_version_newer = is_newer_version(meta.version, mod.local_version)

        if is_timestamp_flagged or is_version_newer:
            logger.debug(
                "UPDATE %s: local=%s, nexus=%s (source=%s, ts_flag=%s, ver_flag=%s)",
                mod.display_name,
                mod.local_version,
                meta.version,
                mod.source,
                is_timestamp_flagged,
                is_version_newer,
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
                    "timestamp_only": is_timestamp_flagged and not is_version_newer,
                    "local_filename": mod.source_archive,
                }
            )
        else:
            logger.debug(
                "OK %s: local=%s, nexus=%s",
                mod.display_name,
                mod.local_version,
                meta.version,
            )

    # Resolve file IDs for downloads and persist back to DB
    if updates:
        await _resolve_file_ids(client, game_domain, updates)
        _persist_resolved_file_ids(updates, session, game_id)

    logger.info("Update check complete: %d updates from %d mods", len(updates), len(tracked))

    result = UpdateResult(total_checked=len(tracked), updates=updates)
    _cache_update_result(game_id, result, session)
    return result


def check_cached_updates(
    game_id: int,
    game_domain: str,
    session: Session,
) -> UpdateResult:
    """Return cached update results, falling back to offline version comparison.

    Reads the cached result from the last check_all_updates() call.
    If no cache exists, falls back to comparing local versions against
    last-refreshed NexusModMeta.version (the old behavior).
    """
    cached = _load_cached_result(game_id, session)
    if cached is not None:
        return cached

    # Fallback: offline version comparison (no timestamp data available)
    tracked = collect_tracked_mods(game_id, game_domain, session)
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
