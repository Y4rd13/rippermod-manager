"""Update checking service with timestamp-based and version-based paths."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlmodel import Session, select

from chat_nexus_mod_manager.matching.filename_parser import is_newer_version
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.nexus.client import NexusClient

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_REQUESTS = 5


@dataclass
class UpdateResult:
    """Container for update check results with total count."""

    total_checked: int = 0
    updates: list[dict[str, Any]] = field(default_factory=list)


def _find_best_matching_file(
    installed_mod: InstalledMod,
    nexus_files: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find the best matching Nexus file for an installed mod.

    Priority:
    1. Exact upload_timestamp match -> return latest file in same category
    2. nexus_file_id match -> return that file
    3. Most recent MAIN file (category_id == 1)
    4. Most recent file of any category
    """
    if not nexus_files:
        return None

    # Priority 1: exact timestamp match
    if installed_mod.upload_timestamp:
        matched_file = None
        for f in nexus_files:
            if f.get("uploaded_timestamp") == installed_mod.upload_timestamp:
                matched_file = f
                break

        if matched_file:
            category = matched_file.get("category_id")
            same_category = [f for f in nexus_files if f.get("category_id") == category]
            if same_category:
                return max(same_category, key=lambda f: f.get("uploaded_timestamp", 0))
            return matched_file

    # Priority 2: file_id match
    if installed_mod.nexus_file_id:
        for f in nexus_files:
            if f.get("file_id") == installed_mod.nexus_file_id:
                return f

    # Priority 3: most recent MAIN file (category_id == 1)
    main_files = [f for f in nexus_files if f.get("category_id") == 1]
    if main_files:
        return max(main_files, key=lambda f: f.get("uploaded_timestamp", 0))

    # Priority 4: most recent file of any category
    return max(nexus_files, key=lambda f: f.get("uploaded_timestamp", 0))


def _check_update_for_installed_mod(
    installed_mod: InstalledMod,
    nexus_files: list[dict[str, Any]],
    mod_meta: NexusModMeta | None,
) -> dict[str, Any] | None:
    """Check if an installed mod has an update available.

    Returns a dict with update info, or None if no update.
    """
    best_file = _find_best_matching_file(installed_mod, nexus_files)
    if not best_file:
        return None

    has_update = False
    nexus_version = best_file.get("version", "")
    local_version = installed_mod.installed_version
    local_ts = installed_mod.upload_timestamp
    nexus_ts = best_file.get("uploaded_timestamp")

    # Primary: timestamp comparison
    if local_ts and nexus_ts and nexus_ts > local_ts:
        has_update = True
    # Fallback: semantic version comparison
    elif not local_ts or not nexus_ts:
        if nexus_version and local_version:
            has_update = is_newer_version(nexus_version, local_version)
        elif mod_meta and mod_meta.version and local_version:
            nexus_version = mod_meta.version
            has_update = is_newer_version(nexus_version, local_version)

    if not has_update:
        return None

    nexus_mod_id = installed_mod.nexus_mod_id or 0
    display_name = installed_mod.name
    author = mod_meta.author if mod_meta else ""
    nexus_url = ""
    if mod_meta:
        nexus_url = f"https://www.nexusmods.com/{mod_meta.game_domain}/mods/{nexus_mod_id}"

    return {
        "installed_mod_id": installed_mod.id,
        "mod_group_id": installed_mod.mod_group_id,
        "display_name": display_name,
        "local_version": local_version,
        "nexus_version": nexus_version,
        "nexus_mod_id": nexus_mod_id,
        "nexus_url": nexus_url,
        "author": author,
        "source": "installed",
        "local_timestamp": local_ts,
        "nexus_timestamp": nexus_ts,
    }


async def check_installed_mod_updates(
    game_id: int,
    game_domain: str,
    client: NexusClient,
    session: Session,
) -> UpdateResult:
    """Check updates for installed mods using timestamp comparison.

    Queries InstalledMod where nexus_mod_id IS NOT NULL, groups by nexus_mod_id
    to avoid duplicate API calls. Uses concurrent requests with a semaphore
    to respect Nexus API rate limits.
    """
    installed_mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game_id,
            InstalledMod.nexus_mod_id.is_not(None),  # type: ignore[union-attr]
        )
    ).all()

    if not installed_mods:
        return UpdateResult()

    # Group by nexus_mod_id to avoid duplicate API calls
    groups: dict[int, list[InstalledMod]] = {}
    for mod in installed_mods:
        mid = mod.nexus_mod_id
        assert mid is not None
        groups.setdefault(mid, []).append(mod)

    total_checked = len(installed_mods)

    # Fetch files concurrently with rate limit
    sem = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

    async def fetch_files(nid: int) -> tuple[int, dict[str, Any] | None]:
        async with sem:
            try:
                return nid, await client.get_mod_files(game_domain, nid)
            except (httpx.HTTPError, ValueError):
                logger.warning("Failed to fetch files for mod %d", nid)
                return nid, None

    results = await asyncio.gather(*(fetch_files(nid) for nid in groups))

    updates: list[dict[str, Any]] = []
    seen_nexus_ids: set[int] = set()

    for nexus_mod_id, files_response in results:
        if files_response is None:
            continue
        nexus_files = files_response.get("files", [])

        meta = session.exec(
            select(NexusModMeta).where(NexusModMeta.nexus_mod_id == nexus_mod_id)
        ).first()

        for mod in groups[nexus_mod_id]:
            if nexus_mod_id in seen_nexus_ids:
                continue
            result = _check_update_for_installed_mod(mod, nexus_files, meta)
            if result:
                updates.append(result)
                seen_nexus_ids.add(nexus_mod_id)

    return UpdateResult(total_checked=total_checked, updates=updates)


def check_correlation_updates(
    game_id: int,
    session: Session,
) -> UpdateResult:
    """Check updates via correlation pipeline using semantic version comparison.

    Uses is_newer_version() instead of simple != to avoid false positives
    like "1.0" vs "1.0.0".
    """
    correlations = session.exec(
        select(ModNexusCorrelation, ModGroup, NexusDownload)
        .join(ModGroup, ModNexusCorrelation.mod_group_id == ModGroup.id)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .where(ModGroup.game_id == game_id)
    ).all()

    total_checked = len(correlations)
    updates: list[dict[str, Any]] = []
    for _corr, group, download in correlations:
        meta = session.exec(
            select(NexusModMeta).where(NexusModMeta.nexus_mod_id == download.nexus_mod_id)
        ).first()
        if not meta or not meta.version or not download.version:
            continue
        if is_newer_version(meta.version, download.version):
            updates.append(
                {
                    "installed_mod_id": None,
                    "mod_group_id": group.id,
                    "display_name": group.display_name,
                    "local_version": download.version,
                    "nexus_version": meta.version,
                    "nexus_mod_id": download.nexus_mod_id,
                    "nexus_url": download.nexus_url,
                    "author": meta.author,
                    "source": "correlation",
                    "local_timestamp": None,
                    "nexus_timestamp": None,
                }
            )

    return UpdateResult(total_checked=total_checked, updates=updates)
