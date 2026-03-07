"""Shared helpers for creating/updating Nexus mod records."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

import httpx
from sqlmodel import Session, select

from rippermod_manager.models.nexus import NexusDownload, NexusModMeta, NexusModRequirement
from rippermod_manager.services.settings_helpers import get_setting, set_setting

if TYPE_CHECKING:
    from rippermod_manager.nexus.client import NexusClient

logger = logging.getLogger(__name__)


# -- GraphQL → REST adapter functions ----------------------------------------


def _iso_to_epoch(value: str | int | None) -> int | None:
    """Convert ISO 8601 timestamp or Unix epoch to Unix epoch seconds.

    The Nexus GraphQL API returns dates as ISO strings in some queries
    (e.g. mod fields) but as Unix epoch integers in others (e.g. mod files).
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


def graphql_mod_to_rest_info(gql_mod: dict[str, Any]) -> dict[str, Any]:
    """Convert a GraphQL Mod object to a REST-compatible dict for upsert_nexus_mod()."""
    return {
        "name": gql_mod.get("name", ""),
        "summary": gql_mod.get("summary", ""),
        "description": gql_mod.get("description", ""),
        "version": gql_mod.get("version", ""),
        "author": gql_mod.get("author", ""),
        "endorsement_count": gql_mod.get("endorsements", 0),
        "mod_downloads": gql_mod.get("downloads", 0),
        "category_id": gql_mod.get("category", ""),
        "picture_url": gql_mod.get("pictureUrl", ""),
        "created_timestamp": _iso_to_epoch(gql_mod.get("createdAt")),
        "updated_timestamp": _iso_to_epoch(gql_mod.get("updatedAt")),
    }


def graphql_file_to_rest_file(gql_file: dict[str, Any]) -> dict[str, Any]:
    """Convert a GraphQL ModFile object to a REST-compatible file dict."""
    return {
        "file_id": gql_file.get("fileId"),
        "file_name": gql_file.get("name", ""),
        "version": gql_file.get("version", ""),
        "category_id": gql_file.get("categoryId"),
        "category_name": gql_file.get("category", ""),
        "uploaded_timestamp": _iso_to_epoch(gql_file.get("date")),
        "size_in_bytes": gql_file.get("size") or 0,
        "description": gql_file.get("description"),
        "content_preview_link": gql_file.get("contentPreviewLink"),
    }


def graphql_hash_to_mod_info(
    hit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], int | None]:
    """Convert a GraphQL FileHash result to (mod_info, file_info, mod_id).

    Returns REST-compatible dicts suitable for upsert_nexus_mod().
    """
    mod_file = hit.get("modFile") or {}
    mod = mod_file.get("mod") or {}
    mod_id = mod.get("modId")

    mod_info = {
        "name": mod.get("name", ""),
        "summary": mod.get("summary", ""),
        "version": mod.get("version", ""),
        "author": mod.get("author", ""),
        "endorsement_count": mod.get("endorsements", 0),
        "mod_downloads": mod.get("downloads", 0),
        "category_id": mod.get("category", ""),
        "picture_url": mod.get("pictureUrl", ""),
        "created_timestamp": _iso_to_epoch(mod.get("createdAt")),
        "updated_timestamp": _iso_to_epoch(mod.get("updatedAt")),
    }

    file_info = {
        "file_id": mod_file.get("fileId"),
        "file_name": mod_file.get("name") or hit.get("fileName", ""),
        "version": mod_file.get("version", ""),
        "category_id": mod_file.get("categoryId"),
    }

    return mod_info, file_info, mod_id


def store_uid_from_gql(session: Session, nexus_mod_id: int, uid: str) -> None:
    """Store the global UID in NexusModMeta if not already set."""
    if not uid:
        return
    meta = session.exec(
        select(NexusModMeta).where(NexusModMeta.nexus_mod_id == nexus_mod_id)
    ).first()
    if meta and not meta.uid:
        meta.uid = uid


def get_stored_uid(session: Session, nexus_mod_id: int) -> str | None:
    """Get stored UID for a mod, or None if not yet stored."""
    meta = session.exec(
        select(NexusModMeta).where(NexusModMeta.nexus_mod_id == nexus_mod_id)
    ).first()
    if meta and meta.uid:
        return meta.uid
    return None


def extract_dlc_requirements(gql_mod: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract DLC requirements from a GraphQL mod response into a serialisable list."""
    mod_reqs = gql_mod.get("modRequirements") or {}
    dlc_nodes = mod_reqs.get("dlcRequirements") or []
    result: list[dict[str, Any]] = []
    for node in dlc_nodes:
        expansion = node.get("gameExpansion") or {}
        result.append(
            {
                "expansion_name": expansion.get("name", ""),
                "expansion_id": expansion.get("id"),
                "notes": node.get("notes", ""),
            }
        )
    return result


def upsert_mod_requirements(
    session: Session,
    nexus_mod_id: int,
    gql_requirements: list[dict[str, Any]],
    *,
    reverse_requirements: list[dict[str, Any]] | None = None,
    dlc_requirements: list[dict[str, Any]] | None = None,
) -> None:
    """Replace requirements for a mod from GraphQL modRequirements data."""
    # Delete existing forward requirements (None = no fresh data, skip; [] = cleared upstream)
    if gql_requirements is not None:
        existing_fwd = session.exec(
            select(NexusModRequirement).where(
                NexusModRequirement.nexus_mod_id == nexus_mod_id,
                NexusModRequirement.is_reverse.is_(False),  # type: ignore[union-attr]
            )
        ).all()
        for req in existing_fwd:
            session.delete(req)

        for req_data in gql_requirements:
            url = req_data.get("url", "")
            raw_mod_id = req_data.get("modId")
            try:
                required_mod_id = int(raw_mod_id) if raw_mod_id else None
            except (ValueError, TypeError):
                required_mod_id = None
            is_external = req_data.get("externalRequirement", False)

            session.add(
                NexusModRequirement(
                    nexus_mod_id=nexus_mod_id,
                    required_mod_id=required_mod_id,
                    mod_name=req_data.get("modName", ""),
                    url=url,
                    notes=req_data.get("notes", ""),
                    is_external=is_external,
                    is_reverse=False,
                )
            )

    # Reverse requirements: mods that depend on this mod
    if reverse_requirements is not None:
        existing_rev = session.exec(
            select(NexusModRequirement).where(
                NexusModRequirement.nexus_mod_id == nexus_mod_id,
                NexusModRequirement.is_reverse.is_(True),  # type: ignore[union-attr]
            )
        ).all()
        for req in existing_rev:
            session.delete(req)

        for req_data in reverse_requirements:
            raw_mod_id = req_data.get("modId")
            try:
                required_mod_id = int(raw_mod_id) if raw_mod_id else None
            except (ValueError, TypeError):
                required_mod_id = None

            session.add(
                NexusModRequirement(
                    nexus_mod_id=nexus_mod_id,
                    required_mod_id=required_mod_id,
                    mod_name=req_data.get("modName", ""),
                    url=req_data.get("url", ""),
                    notes=req_data.get("notes", ""),
                    is_external=req_data.get("externalRequirement", False),
                    is_reverse=True,
                )
            )

    # DLC requirements: store as JSON on NexusModMeta
    if dlc_requirements is not None:
        meta = session.exec(
            select(NexusModMeta).where(NexusModMeta.nexus_mod_id == nexus_mod_id)
        ).first()
        if meta:
            meta.dlc_requirements = json.dumps(dlc_requirements)


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
            session.flush()
        return categories
    except httpx.HTTPError:
        logger.warning("Failed to fetch game categories for %s", game_domain, exc_info=True)
        return {}
