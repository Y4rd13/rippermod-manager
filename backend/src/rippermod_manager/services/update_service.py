"""Unified update checking across installed, correlated, endorsed, and tracked mods.

Strategy — timestamp-first detection:
1. Collect ALL nexus_mod_ids from every source with local version + file mtime
2. Deduplicate: installed > correlation > endorsed > tracked
3. Scan downloaded_mods/ archives for ground-truth local versions
4. Fetch recently updated mods (1 API call: get_updated_mods("1m"))
5. Flag mods needing metadata refresh (timestamp change OR missing meta)
6. Refresh NexusModMeta only for flagged mods
7. Detect updates via TIMESTAMP comparison (primary) + VERSION comparison (secondary)
8. Resolve file IDs and filter false positives
9. Cache results in AppSetting for the GET endpoint
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlmodel import Session, select

from rippermod_manager.matching.filename_parser import (
    ParsedFilename,
    is_newer_version,
    parse_mod_filename,
)
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.mod import ModFile, ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModMeta
from rippermod_manager.nexus.client import NexusClient
from rippermod_manager.services.download_dates import archive_download_dates
from rippermod_manager.services.nexus_helpers import match_local_to_nexus_file
from rippermod_manager.services.settings_helpers import get_setting, set_setting
from rippermod_manager.utils.paths import build_file_path, to_native_path

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 5
_CACHE_KEY_PREFIX = "update_cache_"
_CACHE_TTL = timedelta(hours=24)
_ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar"}


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
    local_file_mtime: int | None = None
    source_archive: str = ""


@dataclass
class UpdateResult:
    total_checked: int = 0
    updates: list[dict[str, Any]] = field(default_factory=list)


def batch_group_file_mtimes(
    group_ids: list[int],
    install_path: str,
    session: Session,
) -> dict[int, int]:
    """Get the earliest file mtime for multiple mod groups in a single query.

    Returns a dict mapping mod_group_id → min mtime (unix timestamp).
    Groups with no files or no stat-able files are omitted.
    """
    if not group_ids or not install_path:
        return {}

    # Single query: fetch one representative file path per group
    rows = session.exec(
        select(ModFile.mod_group_id, ModFile.file_path).where(
            ModFile.mod_group_id.in_(group_ids)  # type: ignore[union-attr]
        )
    ).all()

    # Group file paths by mod_group_id
    paths_by_group: dict[int, list[str]] = {}
    for gid, fpath in rows:
        if gid is None:
            continue
        paths_by_group.setdefault(gid, []).append(fpath)

    result: dict[int, int] = {}
    for gid, paths in paths_by_group.items():
        min_mtime: int | None = None
        for rel_path in paths[:5]:
            full_path = build_file_path(install_path, rel_path)
            try:
                st = os.stat(full_path)
                mtime = int(st.st_mtime)
                if min_mtime is None or mtime < min_mtime:
                    min_mtime = mtime
            except OSError:
                continue
        if min_mtime is not None:
            result[gid] = min_mtime
    return result


def _scan_download_archives(install_path: str) -> dict[int, ParsedFilename]:
    """Scan the downloaded_mods/ staging folder for Nexus archive filenames.

    Returns a dict keyed by nexus_mod_id with the parsed filename info.
    When multiple archives exist for the same mod, keeps the one with the
    latest upload_timestamp.
    """
    staging = Path(to_native_path(install_path)) / "downloaded_mods"
    if not staging.is_dir():
        return {}

    results: dict[int, ParsedFilename] = {}
    try:
        for entry in staging.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in _ARCHIVE_EXTENSIONS:
                continue
            parsed = parse_mod_filename(entry.name)
            if parsed.nexus_mod_id is None:
                continue
            mid = parsed.nexus_mod_id
            existing = results.get(mid)
            if existing is None:
                results[mid] = parsed
                continue
            newer_ts = parsed.upload_timestamp and (
                not existing.upload_timestamp or parsed.upload_timestamp > existing.upload_timestamp
            )
            if newer_ts:
                results[mid] = parsed
    except OSError:
        logger.warning("Failed to scan downloaded_mods at %s", staging)

    return results


def collect_tracked_mods(
    game_id: int,
    game_domain: str,
    session: Session,
    install_path: str = "",
) -> dict[int, TrackedMod]:
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

    # Source 2: Correlated mods (Nexus Matched)
    correlations = session.exec(
        select(ModNexusCorrelation, ModGroup, NexusDownload)
        .join(ModGroup, ModNexusCorrelation.mod_group_id == ModGroup.id)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .where(ModGroup.game_id == game_id)
    ).all()

    # Batch-query file mtimes for all mod groups (single DB query + stat calls)
    all_group_ids: list[int] = []
    for mod in installed:
        if mod.mod_group_id is not None:
            all_group_ids.append(mod.mod_group_id)
    for _corr, group, _dl in correlations:
        if group.id is not None:
            all_group_ids.append(group.id)
    mtime_map = batch_group_file_mtimes(all_group_ids, install_path, session)

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
            local_file_mtime=(
                mod.upload_timestamp
                if mod.upload_timestamp
                else mtime_map.get(mod.mod_group_id)
                if mod.mod_group_id
                else None
            ),
            source_archive=mod.source_archive,
        )

    # Build a lookup so Source 3 can reuse mtimes from correlated groups
    corr_mtime_by_nexus_id: dict[int, int | None] = {}
    for _corr, group, dl in correlations:
        mid = dl.nexus_mod_id
        if mid in mods:
            continue
        parsed = parse_mod_filename(dl.file_name) if dl.file_name else None
        local_v = (parsed.version if parsed and parsed.version else None) or dl.version
        if not local_v:
            continue
        mtime = mtime_map.get(group.id) if group.id else None
        corr_mtime_by_nexus_id[mid] = mtime
        mods[mid] = TrackedMod(
            nexus_mod_id=mid,
            local_version=local_v,
            display_name=group.display_name,
            source="correlation",
            mod_group_id=group.id,
            nexus_url=dl.nexus_url,
            local_file_mtime=mtime,
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
            local_file_mtime=corr_mtime_by_nexus_id.get(mid),
            source_archive=dl.file_name,
        )

    # Enrich with downloaded archives (ground truth versions)
    if install_path:
        archives = _scan_download_archives(install_path)
        if archives:
            logger.info(
                "Archive scan: found %d archives with Nexus filenames in downloaded_mods/",
                len(archives),
            )
            for mid, parsed in archives.items():
                if mid not in mods:
                    continue
                existing = mods[mid]
                new_version = parsed.version or existing.local_version
                new_ts = parsed.upload_timestamp or existing.upload_timestamp
                if new_version != existing.local_version or new_ts != existing.upload_timestamp:
                    mods[mid] = TrackedMod(
                        nexus_mod_id=existing.nexus_mod_id,
                        local_version=new_version,
                        display_name=existing.display_name,
                        source=existing.source,
                        installed_mod_id=existing.installed_mod_id,
                        mod_group_id=existing.mod_group_id,
                        upload_timestamp=new_ts,
                        nexus_url=existing.nexus_url,
                        local_file_mtime=existing.local_file_mtime,
                        source_archive=existing.source_archive,
                    )

    mtime_count = sum(1 for m in mods.values() if m.local_file_mtime is not None)
    installed_count = sum(1 for m in mods.values() if m.source == "installed")
    corr_count = sum(1 for m in mods.values() if m.source == "correlation")
    endorsed_tracked = sum(1 for m in mods.values() if m.source in ("endorsed", "tracked"))
    logger.info(
        "Collecting tracked mods: %d installed, %d correlated, %d endorsed/tracked",
        installed_count,
        corr_count,
        endorsed_tracked,
    )
    logger.info("File mtime: obtained for %d/%d mod groups", mtime_count, len(mods))

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

                local_fn = update.get("source_archive", "")
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
                    # Store resolved file timestamp for the false-positive filter
                    # (separate from nexus_timestamp which shows the mod's last update).
                    update["_resolved_file_ts"] = best.get("uploaded_timestamp")
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
    install_path: str = "",
) -> UpdateResult:
    """Unified update check with timestamp-first detection.

    1. Collect tracked mods with local_file_mtime + local_version
    2. Fetch recently updated mods from Nexus (1 API call)
    3. Flag mods needing metadata refresh (timestamp OR missing meta)
    4. Refresh metadata for flagged mods
    5. Detect updates: timestamp comparison (primary) + version comparison (secondary)
    6. Resolve file IDs, filter false positives
    7. Cache result for the GET endpoint
    """
    tracked = collect_tracked_mods(game_id, game_domain, session, install_path)
    if not tracked:
        return UpdateResult()

    # 1 API call: get all mods updated in last month
    file_update_map: dict[int, int] = {}
    try:
        updated_entries = await client.get_updated_mods(game_domain, "1m")
        for entry in updated_entries:
            file_update_map[entry["mod_id"]] = entry.get("latest_file_update", 0)
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to fetch recently updated mods", exc_info=True)

    overlap_count = sum(1 for mid in tracked if mid in file_update_map)
    logger.info(
        "get_updated_mods: %d mods updated in last month, %d overlap with tracked",
        len(file_update_map),
        overlap_count,
    )

    # Load pre-refresh updated_at baselines for our tracked mods
    tracked_ids = list(tracked.keys())
    meta_rows = session.exec(
        select(NexusModMeta).where(
            NexusModMeta.nexus_mod_id.in_(tracked_ids)  # type: ignore[union-attr]
        )
    ).all()
    baseline_map: dict[int, datetime | None] = {m.nexus_mod_id: m.updated_at for m in meta_rows}

    # Flag mods needing metadata refresh:
    # - Mods in file_update_map where latest_file_update > baseline
    # - Mods WITHOUT any NexusModMeta entry (fixes the line 305 bug)
    timestamp_flagged: set[int] = set()
    missing_meta: set[int] = set()
    for mid in tracked:
        if mid not in baseline_map:
            missing_meta.add(mid)
            continue
        latest_file_ts = file_update_map.get(mid)
        if latest_file_ts is None:
            # Not updated in last month — still check via version later
            continue
        baseline = baseline_map[mid]
        if baseline is None:
            timestamp_flagged.add(mid)
        else:
            baseline_utc = baseline.replace(tzinfo=UTC) if baseline.tzinfo is None else baseline
            baseline_epoch = int(baseline_utc.timestamp())
            if latest_file_ts > baseline_epoch:
                timestamp_flagged.add(mid)

    to_refresh = timestamp_flagged | missing_meta
    logger.info(
        "Metadata refresh: %d mods flagged (%d timestamp, %d missing meta)",
        len(to_refresh),
        len(timestamp_flagged),
        len(missing_meta),
    )

    if to_refresh:
        await _refresh_metadata(client, game_domain, to_refresh, session)

    # Reload metadata after refresh
    meta_rows = session.exec(
        select(NexusModMeta).where(
            NexusModMeta.nexus_mod_id.in_(tracked_ids)  # type: ignore[union-attr]
        )
    ).all()
    meta_map = {m.nexus_mod_id: m for m in meta_rows}

    # Compute download dates for accurate detection.
    # User's rule: if Nexus updated AFTER download, always flag for update.
    download_date_map: dict[int, int] = {}
    archive_names = {m.source_archive for m in tracked.values() if m.source_archive}
    if archive_names and install_path:
        raw_dates = archive_download_dates(session, game_id, install_path, archive_names)
        archive_epoch = {fn: int(dt.timestamp()) for fn, dt in raw_dates.items()}
        for mid, mod in tracked.items():
            if mod.source_archive and mod.source_archive in archive_epoch:
                download_date_map[mid] = archive_epoch[mod.source_archive]

    # Fallback: InstalledMod.installed_at for mods without archive download dates
    remaining_installed = {
        mod.installed_mod_id: mid
        for mid, mod in tracked.items()
        if mid not in download_date_map and mod.installed_mod_id is not None
    }
    if remaining_installed:
        inst_rows = session.exec(
            select(InstalledMod.id, InstalledMod.installed_at).where(
                InstalledMod.id.in_(list(remaining_installed.keys()))
            )
        ).all()
        for inst_id, inst_at in inst_rows:
            if inst_at and inst_id in remaining_installed:
                mid = remaining_installed[inst_id]
                dt = inst_at.replace(tzinfo=UTC) if inst_at.tzinfo is None else inst_at
                download_date_map[mid] = int(dt.timestamp())

    dl_count = sum(1 for mid in tracked if mid in download_date_map)
    logger.info("Download dates: obtained for %d/%d tracked mods", dl_count, len(tracked))

    # Detect updates via THREE methods
    updates: list[dict[str, Any]] = []
    ts_detections = 0
    ver_detections = 0
    both_detections = 0
    dl_detections = 0

    for mid, mod in tracked.items():
        meta = meta_map.get(mid)
        if not meta or not meta.version:
            logger.debug("Skip mod %d (%s): no metadata version", mid, mod.display_name)
            continue

        # a) TIMESTAMP comparison (primary)
        is_ts_flagged = False
        nexus_update_ts: int | None = None
        if mid in file_update_map:
            nexus_update_ts = file_update_map[mid]
        elif meta.updated_at is not None:
            updated = meta.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            nexus_update_ts = int(updated.timestamp())

        if mod.local_file_mtime is not None and nexus_update_ts is not None:
            # Precise comparison: Nexus file timestamp vs local file mtime
            if nexus_update_ts > mod.local_file_mtime:
                is_ts_flagged = True
        elif mid in timestamp_flagged:
            # Fallback for mods without local files (endorsed/tracked):
            # Nexus updated since our last metadata refresh
            is_ts_flagged = True

        # b) VERSION comparison (secondary)
        is_version_newer = is_newer_version(meta.version, mod.local_version)
        is_version_equal = not is_version_newer and not is_newer_version(
            mod.local_version, meta.version
        )

        # c) DOWNLOAD DATE comparison (user's rule: always flag if Nexus updated
        # after the user downloaded the mod — regardless of version strings)
        download_date = download_date_map.get(mid)
        is_dl_newer = (
            download_date is not None
            and nexus_update_ts is not None
            and nexus_update_ts > download_date
        )

        # file_update_map entries come from Nexus get_updated_mods API
        # (latest_file_update) — only changes when a new file is uploaded.
        # meta.updated_at changes on any metadata edit — unreliable.
        # Only suppress same-version detections for the unreliable source.
        is_file_update = mid in file_update_map

        if (
            is_version_newer
            or is_dl_newer
            or (is_ts_flagged and (is_file_update or not is_version_equal))
        ):
            if is_dl_newer and is_version_newer:
                detection = "both"
                both_detections += 1
            elif is_dl_newer:
                detection = "timestamp"
                dl_detections += 1
            elif is_ts_flagged and is_version_newer:
                detection = "both"
                both_detections += 1
            elif is_ts_flagged:
                detection = "timestamp"
                ts_detections += 1
            else:
                detection = "version"
                ver_detections += 1

            logger.debug(
                "MOD %s (id=%d): local_v=%s, nexus_v=%s, local_mtime=%s, nexus_ts=%s -> %s",
                mod.display_name,
                mid,
                mod.local_version,
                meta.version,
                mod.local_file_mtime,
                nexus_update_ts,
                detection,
            )
            if detection == "version":
                reason = f"Newer version available: v{meta.version}"
            elif detection == "timestamp":
                reason = "Newer file uploaded on Nexus"
            else:  # "both"
                reason = f"Newer version v{meta.version} + newer file on Nexus"

            updates.append(
                {
                    "installed_mod_id": mod.installed_mod_id,
                    "mod_group_id": mod.mod_group_id,
                    "display_name": mod.display_name,
                    "local_version": mod.local_version,
                    "nexus_version": meta.version,
                    "_initial_nexus_version": meta.version,
                    "_is_file_update": is_file_update,
                    "_is_dl_newer": is_dl_newer,
                    "nexus_mod_id": mid,
                    "nexus_file_id": None,
                    "nexus_file_name": "",
                    "nexus_url": mod.nexus_url
                    or f"https://www.nexusmods.com/{game_domain}/mods/{mid}",
                    "author": meta.author,
                    "source": mod.source,
                    "local_timestamp": mod.upload_timestamp,
                    "nexus_timestamp": nexus_update_ts,
                    "detection_method": detection,
                    "source_archive": mod.source_archive,
                    "reason": reason,
                }
            )
        else:
            logger.debug(
                "OK %s: local=%s, nexus=%s",
                mod.display_name,
                mod.local_version,
                meta.version,
            )

    logger.info(
        "Update detection: %d by timestamp, %d by version, %d by both, %d by download-date",
        ts_detections,
        ver_detections,
        both_detections,
        dl_detections,
    )

    # Resolve file IDs for downloads, persist back to DB, and filter false positives
    if updates:
        await _resolve_file_ids(client, game_domain, updates)
        # Persist file IDs before filtering — we want the mapping even for
        # mods that turn out to be false positives (useful for future checks).
        _persist_resolved_file_ids(updates, session, game_id)

        # Update reason if resolved version differs from initial detection
        for u in updates:
            resolved_v = u.get("nexus_version", "")
            initial_v = u.get("_initial_nexus_version", resolved_v)
            if resolved_v and resolved_v != initial_v:
                u["reason"] = f"Newer version available: v{resolved_v}"

        # Filter false positives after file resolution.
        #
        # Multi-edition mods (e.g. Lite / Enhanced / Customizable on the
        # same Nexus page) can trigger false updates: the mod-page version
        # may be "3.0" while the user's installed edition is still "2.6".
        # File resolution correctly identifies the user's file and version,
        # so we compare the *resolved* version + timestamp against local.
        filtered: list[dict[str, Any]] = []
        for u in updates:
            # Download-date detections bypass the filter entirely.
            # User's rule: if Nexus updated after download, always flag.
            if u.get("_is_dl_newer"):
                filtered.append(u)
                continue

            resolved_nexus_v = u.get("nexus_version", "")
            local_v = u.get("local_version", "")
            is_file_upd = u.get("_is_file_update", False)
            mid = u["nexus_mod_id"]
            # Use the resolved file's upload timestamp (not nexus_timestamp
            # which now holds the mod's last-updated time for display).
            resolved_file_ts = u.get("_resolved_file_ts")
            local_mtime = tracked[mid].local_file_mtime

            if resolved_nexus_v and local_v and not is_newer_version(resolved_nexus_v, local_v):
                if not is_file_upd:
                    logger.debug(
                        "Filtered (resolved version not newer): %s — nexus=%s, local=%s",
                        u["display_name"],
                        resolved_nexus_v,
                        local_v,
                    )
                    continue
                # File-update signal exists (get_updated_mods confirmed a new
                # file upload) — but the resolved file may belong to a
                # *different* edition.  Verify that the resolved file is
                # actually newer than the local file before keeping.
                if (
                    resolved_file_ts is not None
                    and local_mtime is not None
                    and resolved_file_ts <= local_mtime
                ):
                    logger.debug(
                        "Filtered (same-version, file not newer): %s — file_ts=%d <= local_ts=%d",
                        u["display_name"],
                        resolved_file_ts,
                        local_mtime,
                    )
                    continue
                # Endorsed/tracked mods without local files: nothing to update
                # locally, even if Nexus has a new file with the same version.
                if local_mtime is None and u.get("source") in ("endorsed", "tracked"):
                    logger.debug(
                        "Filtered (same-version, no local files): %s",
                        u["display_name"],
                    )
                    continue
                # Trust the file-update signal from get_updated_mods when
                # timestamps are unavailable for precise comparison.
                logger.debug(
                    "Kept (file-update signal, same version): %s",
                    u["display_name"],
                )

            filtered.append(u)
        updates = filtered

    logger.info(
        "Update check complete: %d updates from %d tracked mods",
        len(updates),
        len(tracked),
    )

    # Strip internal fields (prefixed with _) before caching/returning
    clean_updates = [{k: v for k, v in u.items() if not k.startswith("_")} for u in updates]

    result = UpdateResult(total_checked=len(tracked), updates=clean_updates)
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
                    "detection_method": "version",
                    "source_archive": mod.source_archive,
                    "reason": f"Newer version available: v{meta.version}",
                }
            )

    return UpdateResult(total_checked=len(tracked), updates=updates)
