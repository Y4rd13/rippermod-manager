"""Shared helpers for creating/updating Nexus mod records."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from sqlmodel import Session, select

from rippermod_manager.models.nexus import NexusDownload, NexusModMeta
from rippermod_manager.services.settings_helpers import get_setting, set_setting

if TYPE_CHECKING:
    from rippermod_manager.nexus.client import NexusClient

logger = logging.getLogger(__name__)


def match_local_to_nexus_file(
    local_filename: str,
    nexus_files: list[dict[str, Any]],
    *,
    parsed_version: str | None = None,
    parsed_timestamp: int | None = None,
    strict: bool = False,
) -> dict[str, Any] | None:
    """Match a local filename against Nexus file list entries.

    Strategy (in priority order):
    1. Exact stem match (case-insensitive)
    2. Timestamp match against ``uploaded_timestamp``
    3. Version + category match (prefer MAIN files, category_id=1)
    4. Fallback: most recent MAIN file, or most recent active file
       (skipped when ``strict=True``)

    Always excludes archived files (category_id=7).
    """
    active = [f for f in nexus_files if f.get("category_id") != 7]
    if not active:
        return None

    local_stem = PurePosixPath(local_filename).stem.lower()

    # 1. Exact stem match
    if local_stem:
        for nf in active:
            nexus_name = nf.get("file_name") or nf.get("name", "")
            if PurePosixPath(nexus_name).stem.lower() == local_stem:
                return nf

    # 2. Timestamp match
    if parsed_timestamp:
        for nf in active:
            if nf.get("uploaded_timestamp") == parsed_timestamp:
                return nf

    # 3. Version + category match
    if parsed_version:
        version_matches = [nf for nf in active if nf.get("version") == parsed_version]
        main_vm = [nf for nf in version_matches if nf.get("category_id") == 1]
        if main_vm:
            return main_vm[0]
        if version_matches:
            return version_matches[0]

    if strict:
        return None

    # 4. Fallback: most recent MAIN file, or most recent active file
    main_files = [nf for nf in active if nf.get("category_id") == 1]
    if main_files:
        return max(main_files, key=lambda f: f.get("uploaded_timestamp", 0))
    return max(active, key=lambda f: f.get("uploaded_timestamp", 0))


def upsert_nexus_mod(
    session: Session,
    game_id: int,
    game_domain: str,
    mod_id: int,
    info: dict[str, Any],
    *,
    file_name: str = "",
    file_id: int | None = None,
) -> NexusDownload:
    """Create or update NexusDownload + NexusModMeta from API response data."""
    nexus_url = f"https://www.nexusmods.com/{game_domain}/mods/{mod_id}"
    mod_name = info.get("name", "")
    version = info.get("version", "")

    existing_dl = session.exec(
        select(NexusDownload).where(
            NexusDownload.game_id == game_id,
            NexusDownload.nexus_mod_id == mod_id,
        )
    ).first()

    if not existing_dl:
        dl = NexusDownload(
            game_id=game_id,
            nexus_mod_id=mod_id,
            mod_name=mod_name,
            file_name=file_name,
            file_id=file_id,
            version=version,
            category=str(info.get("category_id", "")),
            nexus_url=nexus_url,
        )
        session.add(dl)
    else:
        dl = existing_dl
        if mod_name:
            dl.mod_name = mod_name
        # NOTE: intentionally do NOT overwrite dl.version — it represents
        # the version at time of discovery (FOMOD/MD5/snapshot) and must
        # be preserved for update detection.
        if file_name and not dl.file_name:
            dl.file_name = file_name
        if file_id and not dl.file_id:
            dl.file_id = file_id
        dl.nexus_url = nexus_url

    # Upsert mod metadata for vector search
    existing_meta = session.exec(
        select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)
    ).first()
    if not existing_meta:
        meta = NexusModMeta(
            nexus_mod_id=mod_id,
            game_domain=game_domain,
            name=mod_name,
            summary=info.get("summary", ""),
            author=info.get("author", ""),
            version=version,
            description=info.get("description", ""),
            endorsement_count=info.get("endorsement_count", 0),
            mod_downloads=info.get("mod_downloads", 0),
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
        if mod_name:
            existing_meta.name = mod_name
        if info.get("summary"):
            existing_meta.summary = info["summary"]
        if version:
            existing_meta.version = version
        if info.get("author"):
            existing_meta.author = info["author"]
        if info.get("description"):
            existing_meta.description = info["description"]
        if info.get("endorsement_count") is not None:
            existing_meta.endorsement_count = info["endorsement_count"]
        if info.get("mod_downloads") is not None:
            existing_meta.mod_downloads = info["mod_downloads"]
        if info.get("picture_url"):
            existing_meta.picture_url = info["picture_url"]
        created_ts = info.get("created_timestamp")
        if created_ts:
            existing_meta.created_at = datetime.fromtimestamp(created_ts, tz=UTC)
        ts = info.get("updated_timestamp")
        if ts:
            existing_meta.updated_at = datetime.fromtimestamp(ts, tz=UTC)

    return dl


def get_cached_game_categories(game_domain: str, session: Session) -> dict[int, str]:
    """Read cached game categories from AppSetting. Returns empty dict if not cached."""
    raw = get_setting(session, f"game_categories_{game_domain}")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {int(k): v for k, v in data.items()}
    except (json.JSONDecodeError, ValueError):
        return {}


async def get_game_categories(
    game_domain: str,
    session: Session,
    *,
    client: NexusClient | None = None,
    api_key: str = "",
) -> dict[int, str]:
    """Fetch game categories, caching in AppSetting. Returns {category_id: name}."""
    from rippermod_manager.nexus.client import NexusClient

    cached = get_cached_game_categories(game_domain, session)
    if cached:
        return cached

    if not client and not api_key:
        return {}

    def _parse_categories(cats: list[dict[str, Any]]) -> dict[int, str]:
        result: dict[int, str] = {}
        for cat in cats:
            cid = cat.get("category_id")
            name = cat.get("name", "")
            if cid is not None and name:
                result[int(cid)] = name
        return result

    try:
        if client:
            info = await client.get_game_info(game_domain)
        else:
            async with NexusClient(api_key) as c:
                info = await c.get_game_info(game_domain)

        categories = _parse_categories(info.get("categories", []))
        if categories:
            set_setting(
                session,
                f"game_categories_{game_domain}",
                json.dumps({str(k): v for k, v in categories.items()}),
            )
            session.commit()
        return categories
    except Exception:
        logger.warning("Failed to fetch game categories for %s", game_domain, exc_info=True)
        return {}
