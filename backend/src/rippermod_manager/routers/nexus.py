import json
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game

if TYPE_CHECKING:
    from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.install import ArchiveContentsResult, ArchiveEntryOut
from rippermod_manager.schemas.nexus import (
    ModActionResult,
    ModDetailOut,
    NexusDownloadBrief,
    NexusModEnrichedOut,
    NexusModFileOut,
    NexusModSearchResult,
    NexusSyncResult,
    SSOPollResult,
    SSOStartResult,
)
from rippermod_manager.services.settings_helpers import get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nexus", tags=["nexus"])


@router.post("/sync-history/{game_name}", response_model=NexusSyncResult)
async def sync_history(game_name: str, session: Session = Depends(get_session)) -> NexusSyncResult:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")

    api_key = get_setting(session, "nexus_api_key")
    if not api_key:
        raise HTTPException(400, "Nexus API key not configured")

    from rippermod_manager.services.nexus_sync import sync_nexus_history

    return await sync_nexus_history(game, api_key, session)


@router.get("/downloads/{game_name}", response_model=list[NexusModEnrichedOut])
def list_downloads(
    game_name: str,
    source: Literal["endorsed", "tracked"] | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[NexusModEnrichedOut]:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")

    from rippermod_manager.models.nexus import NexusDownload, NexusModMeta

    stmt = (
        select(NexusDownload, NexusModMeta)
        .outerjoin(NexusModMeta, NexusDownload.nexus_mod_id == NexusModMeta.nexus_mod_id)
        .where(NexusDownload.game_id == game.id)
    )

    if source == "endorsed":
        stmt = stmt.where(NexusDownload.is_endorsed.is_(True))  # type: ignore[union-attr]
    elif source == "tracked":
        stmt = stmt.where(NexusDownload.is_tracked.is_(True))  # type: ignore[union-attr]

    rows = session.exec(stmt).all()
    return [
        NexusModEnrichedOut(
            id=dl.id,  # type: ignore[arg-type]
            nexus_mod_id=dl.nexus_mod_id,
            mod_name=dl.mod_name,
            file_name=dl.file_name,
            version=dl.version,
            category=dl.category,
            downloaded_at=dl.downloaded_at,
            nexus_url=dl.nexus_url,
            is_tracked=dl.is_tracked,
            is_endorsed=dl.is_endorsed,
            author=meta.author if meta else "",
            summary=meta.summary if meta else "",
            endorsement_count=meta.endorsement_count if meta else 0,
            picture_url=meta.picture_url if meta else "",
            updated_at=meta.updated_at if meta else None,
        )
        for dl, meta in rows
    ]


@router.get("/downloads/{game_name}/search", response_model=list[NexusDownloadBrief])
def search_downloads(
    game_name: str,
    q: str = Query(min_length=2),
    session: Session = Depends(get_session),
) -> list[NexusDownloadBrief]:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")

    from rippermod_manager.models.nexus import NexusDownload

    escaped_q = q.replace("%", r"\%").replace("_", r"\_")
    stmt = (
        select(NexusDownload)
        .where(
            NexusDownload.game_id == game.id,
            col(NexusDownload.mod_name).ilike(f"%{escaped_q}%", escape="\\"),
        )
        .group_by(NexusDownload.nexus_mod_id)
        .limit(20)
    )
    rows = session.exec(stmt).all()
    return [
        NexusDownloadBrief(
            nexus_mod_id=dl.nexus_mod_id,
            mod_name=dl.mod_name,
            version=dl.version,
            nexus_url=dl.nexus_url,
        )
        for dl in rows
    ]


@router.get("/mods/{game_domain}/{mod_id}/detail", response_model=ModDetailOut)
async def mod_detail(
    game_domain: str, mod_id: int, session: Session = Depends(get_session)
) -> ModDetailOut:
    from rippermod_manager.models.nexus import NexusModFile, NexusModMeta, NexusModRequirement
    from rippermod_manager.nexus.client import NexusClient
    from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
    from rippermod_manager.services.nexus_helpers import (
        extract_dlc_requirements,
        graphql_mod_to_rest_info,
        store_uid_from_gql,
        upsert_mod_requirements,
        upsert_nexus_mod,
    )

    meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()

    api_key = get_setting(session, "nexus_api_key") or ""

    # Fetch mod info via GraphQL if missing
    if not meta or not meta.description:
        if not api_key:
            raise HTTPException(404, "Mod metadata not found and no API key configured")
        async with NexusGraphQLClient(api_key) as gql:
            gql_mod = await gql.get_mod(game_domain, mod_id)
        info = graphql_mod_to_rest_info(gql_mod)
        game = session.exec(select(Game).where(Game.domain_name == game_domain)).first()
        if not game:
            raise HTTPException(404, f"Game domain '{game_domain}' not found")
        upsert_nexus_mod(session, game.id, game_domain, mod_id, info)
        if gql_mod.get("uid"):
            store_uid_from_gql(session, mod_id, gql_mod["uid"])
        # Store requirements (forward + reverse + DLC)
        mod_reqs = gql_mod.get("modRequirements") or {}
        gql_reqs = (mod_reqs.get("nexusRequirements") or {}).get("nodes") or []
        reverse_reqs = (mod_reqs.get("modsRequiringThisMod") or {}).get("nodes") or []
        dlc_reqs = extract_dlc_requirements(gql_mod)
        upsert_mod_requirements(
            session,
            mod_id,
            gql_reqs,
            reverse_requirements=reverse_reqs,
            dlc_requirements=dlc_reqs,
        )
        # Mark requirements as fetched (even if empty) to avoid repeated API calls
        fresh_meta = session.exec(
            select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)
        ).first()
        if fresh_meta:
            fresh_meta.requirements_fetched_at = datetime.now(UTC)
        session.commit()
        meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()

    if not meta:
        raise HTTPException(404, "Mod metadata not found")

    from rippermod_manager.services.nexus_helpers import get_game_categories

    changelogs: dict[str, list[str]] = {}
    files = session.exec(select(NexusModFile).where(NexusModFile.nexus_mod_id == mod_id)).all()

    if api_key:
        needs_insert = len(files) == 0
        needs_refresh = not needs_insert and (
            meta.updated_at is not None
            and (meta.files_updated_at is None or meta.updated_at > meta.files_updated_at)
        )
        needs_backfill = (
            not needs_insert
            and not needs_refresh
            and any(f.description is None or f.content_preview_link is None for f in files)
        )

        try:
            # REST v1 for changelogs + file list (content_preview_link only in REST)
            api_file_list: list[dict[str, Any]] = []
            async with NexusClient(api_key) as rest_client:
                try:
                    changelogs = await rest_client.get_changelogs(game_domain, mod_id)
                except httpx.HTTPError:
                    logger.debug("Failed to fetch changelogs for mod %d", mod_id, exc_info=True)

                if needs_insert or needs_refresh or needs_backfill:
                    try:
                        rest_files = await rest_client.get_mod_files(game_domain, mod_id)
                        api_file_list = rest_files.get("files", [])
                    except httpx.HTTPError:
                        logger.debug("Failed to fetch files for mod %d", mod_id, exc_info=True)

            if api_file_list:
                if needs_insert or needs_refresh:
                    existing_file_ids = {f.file_id for f in files}
                    for af in api_file_list:
                        fid = af.get("file_id")
                        if not fid or fid in existing_file_ids:
                            continue
                        session.add(
                            NexusModFile(
                                nexus_mod_id=mod_id,
                                file_id=fid,
                                file_name=af.get("file_name") or af.get("name", ""),
                                version=af.get("version", ""),
                                category_id=af.get("category_id"),
                                uploaded_timestamp=af.get("uploaded_timestamp"),
                                file_size=af.get("size_in_bytes") or af.get("size") or 0,
                                content_preview_link=af.get("content_preview_link"),
                                description=af.get("description"),
                            )
                        )
                    meta.files_updated_at = meta.updated_at
                    session.commit()
                    files = session.exec(
                        select(NexusModFile).where(NexusModFile.nexus_mod_id == mod_id)
                    ).all()
                else:
                    api_files = {af["file_id"]: af for af in api_file_list if af.get("file_id")}
                    for f in files:
                        if not f.file_id:
                            continue
                        af = api_files.get(f.file_id)
                        if not af:
                            continue
                        if f.description is None:
                            f.description = af.get("description")
                        if f.content_preview_link is None:
                            f.content_preview_link = af.get("content_preview_link")
                    session.commit()
        except httpx.HTTPError:
            logger.debug(
                "Failed to fetch/backfill file metadata for mod %d",
                mod_id,
                exc_info=True,
            )

    # Resolve category_id → name
    category_name = meta.category
    try:
        cat_id = int(meta.category)
        categories = await get_game_categories(game_domain, session, api_key=api_key)
        if cat_id in categories:
            category_name = categories[cat_id]
    except (ValueError, TypeError):
        pass

    from rippermod_manager.models.nexus import NexusDownload

    game_for_dl = session.exec(select(Game).where(Game.domain_name == game_domain)).first()
    dl = None
    if game_for_dl:
        dl = session.exec(
            select(NexusDownload).where(
                NexusDownload.nexus_mod_id == mod_id,
                NexusDownload.game_id == game_for_dl.id,
            )
        ).first()

    # Backfill requirements for mods cached before this feature
    req_rows = session.exec(
        select(NexusModRequirement).where(NexusModRequirement.nexus_mod_id == mod_id)
    ).all()
    if not req_rows and api_key and not meta.requirements_fetched_at:
        try:
            async with NexusGraphQLClient(api_key) as gql:
                gql_mod = await gql.get_mod(game_domain, mod_id)
            mod_reqs = gql_mod.get("modRequirements") or {}
            gql_reqs = (mod_reqs.get("nexusRequirements") or {}).get("nodes") or []
            reverse_reqs = (mod_reqs.get("modsRequiringThisMod") or {}).get("nodes") or []
            dlc_reqs = extract_dlc_requirements(gql_mod)
            upsert_mod_requirements(
                session,
                mod_id,
                gql_reqs,
                reverse_requirements=reverse_reqs,
                dlc_requirements=dlc_reqs,
            )
            req_rows = session.exec(
                select(NexusModRequirement).where(NexusModRequirement.nexus_mod_id == mod_id)
            ).all()
            meta.requirements_fetched_at = datetime.now(UTC)
            session.commit()
        except httpx.HTTPError:
            logger.debug("Failed to backfill requirements for mod %d", mod_id, exc_info=True)

    from rippermod_manager.schemas.nexus import DlcRequirementOut, ModRequirementOut

    requirements = [
        ModRequirementOut(
            nexus_mod_id=r.nexus_mod_id,
            required_mod_id=r.required_mod_id,
            mod_name=r.mod_name,
            url=r.url,
            notes=r.notes,
            is_external=r.is_external,
        )
        for r in req_rows
        if not r.is_reverse
    ]

    dlc_requirements: list[DlcRequirementOut] = []
    try:
        dlc_raw = json.loads(meta.dlc_requirements) if meta.dlc_requirements else []
        dlc_requirements = [
            DlcRequirementOut(
                expansion_name=d.get("expansion_name", ""),
                expansion_id=d.get("expansion_id"),
                notes=d.get("notes", ""),
            )
            for d in dlc_raw
        ]
    except (json.JSONDecodeError, TypeError):
        pass

    nexus_url = f"https://www.nexusmods.com/{game_domain}/mods/{mod_id}"

    return ModDetailOut(
        nexus_mod_id=meta.nexus_mod_id,
        game_domain=meta.game_domain,
        name=meta.name,
        summary=meta.summary,
        description=meta.description,
        author=meta.author,
        version=meta.version,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
        endorsement_count=meta.endorsement_count,
        mod_downloads=meta.mod_downloads,
        category=category_name,
        picture_url=meta.picture_url,
        nexus_url=nexus_url,
        changelogs=changelogs,
        files=[
            NexusModFileOut(
                file_id=f.file_id,
                file_name=f.file_name,
                version=f.version,
                category_id=f.category_id,
                uploaded_timestamp=f.uploaded_timestamp,
                file_size=f.file_size,
                content_preview_link=f.content_preview_link,
                description=f.description,
            )
            for f in files
        ],
        requirements=requirements,
        dlc_requirements=dlc_requirements,
        is_tracked=dl.is_tracked if dl else False,
        is_endorsed=dl.is_endorsed if dl else False,
    )


_SIZE_RE = re.compile(r"^([\d.]+)\s*(B|kB|MB|GB|TB)$")
_SIZE_UNITS = {"B": 1, "kB": 1_000, "MB": 1_000_000, "GB": 1_000_000_000, "TB": 1_000_000_000_000}


def _parse_human_size(s: str) -> int:
    """Parse human-readable size like '222.4 MB' → bytes."""
    m = _SIZE_RE.match(s.strip())
    if not m:
        return 0
    return int(float(m.group(1)) * _SIZE_UNITS.get(m.group(2), 1))


def _nexus_tree_to_entries(
    children: list[dict], path: str = "", depth: int = 0
) -> list[ArchiveEntryOut]:
    """Convert Nexus content_preview JSON tree to ArchiveEntryOut list."""
    if depth > 50:
        return []
    entries: list[ArchiveEntryOut] = []
    for item in children:
        name = item.get("name", "")
        is_dir = item.get("type") == "directory"
        size = _parse_human_size(item.get("size", "0 B")) if not is_dir else 0
        child_entries = _nexus_tree_to_entries(
            item.get("children", []), f"{path}/{name}", depth + 1
        )
        entries.append(ArchiveEntryOut(name=name, is_dir=is_dir, size=size, children=child_entries))
    return entries


def _count_files(nodes: list[ArchiveEntryOut], depth: int = 0) -> tuple[int, int]:
    """Count files and total size in a tree of ArchiveEntryOut nodes."""
    if depth > 50:
        return 0, 0
    count = 0
    total_size = 0
    for n in nodes:
        if n.is_dir:
            c, s = _count_files(n.children, depth + 1)
            count += c
            total_size += s
        else:
            count += 1
            total_size += n.size
    return count, total_size


@router.get("/file-contents-preview", response_model=ArchiveContentsResult)
async def file_contents_preview(url: str = Query(...)) -> ArchiveContentsResult:
    """Proxy a Nexus file content preview URL and return as ArchiveContentsResult."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "file-metadata.nexusmods.com":
        raise HTTPException(400, "Invalid content preview URL")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, "Failed to fetch content preview") from e
    except Exception as e:
        raise HTTPException(502, "Failed to fetch content preview") from e

    children = data.get("children", [])
    tree = _nexus_tree_to_entries(children)
    total_files, total_size = _count_files(tree)

    return ArchiveContentsResult(
        filename="preview",
        total_files=total_files,
        total_size=total_size,
        tree=tree,
    )


@router.get("/search/{game_name}", response_model=list[NexusModSearchResult])
async def search_nexus_mods(
    game_name: str,
    q: str = Query(min_length=2),
    count: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[NexusModSearchResult]:
    """Search Nexus Mods by name via GraphQL v2 text search."""
    game = get_game_or_404(game_name, session)
    api_key = get_setting(session, "nexus_api_key")
    if not api_key:
        raise HTTPException(400, "Nexus API key not configured")

    from rippermod_manager.nexus.client import NexusRateLimitError
    from rippermod_manager.nexus.graphql_client import NexusGraphQLClient, NexusGraphQLError

    try:
        async with NexusGraphQLClient(api_key) as gql:
            results = await gql.search_mods(game.domain_name, q, count=count)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except NexusGraphQLError as e:
        raise HTTPException(400, f"GraphQL error: {e}") from e

    return [
        NexusModSearchResult(
            mod_id=m.get("modId", 0),
            name=m.get("name", ""),
            summary=m.get("summary", ""),
            author=m.get("author", ""),
            version=m.get("version", ""),
            picture_url=m.get("pictureUrl", ""),
            endorsement_count=m.get("endorsements", 0),
            mod_downloads=m.get("downloads", 0),
            category_id=m.get("category"),
            nexus_url=f"https://www.nexusmods.com/{game.domain_name}/mods/{m.get('modId', 0)}",
        )
        for m in results
    ]


def _get_or_create_download(
    session: Session, game_id: int, mod_id: int, game_domain: str
) -> "NexusDownload":
    from rippermod_manager.models.nexus import NexusDownload, NexusModMeta

    dl = session.exec(
        select(NexusDownload).where(
            NexusDownload.game_id == game_id, NexusDownload.nexus_mod_id == mod_id
        )
    ).first()
    if dl:
        return dl

    meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()
    dl = NexusDownload(
        game_id=game_id,
        nexus_mod_id=mod_id,
        mod_name=meta.name if meta else "",
        nexus_url=f"https://www.nexusmods.com/{game_domain}/mods/{mod_id}",
    )
    session.add(dl)
    session.flush()
    return dl


@router.post("/{game_name}/mods/{mod_id}/endorse", response_model=ModActionResult)
async def endorse_mod(
    game_name: str, mod_id: int, session: Session = Depends(get_session)
) -> ModActionResult:
    game = get_game_or_404(game_name, session)
    api_key = get_setting(session, "nexus_api_key")
    if not api_key:
        raise HTTPException(400, "Nexus API key not configured")

    from rippermod_manager.models.nexus import NexusModMeta
    from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError

    meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()
    mod_version = meta.version if meta and meta.version else ""

    try:
        async with NexusClient(api_key) as client:
            await client.endorse_mod(game.domain_name, mod_id, version=mod_version)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Nexus API error: {e}") from e

    dl = _get_or_create_download(session, game.id, mod_id, game.domain_name)  # type: ignore[arg-type]
    dl.is_endorsed = True
    session.commit()
    return ModActionResult(success=True, is_endorsed=True)


@router.post("/{game_name}/mods/{mod_id}/abstain", response_model=ModActionResult)
async def abstain_mod(
    game_name: str, mod_id: int, session: Session = Depends(get_session)
) -> ModActionResult:
    game = get_game_or_404(game_name, session)
    api_key = get_setting(session, "nexus_api_key")
    if not api_key:
        raise HTTPException(400, "Nexus API key not configured")

    from rippermod_manager.models.nexus import NexusModMeta
    from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError

    meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()
    mod_version = meta.version if meta and meta.version else ""

    try:
        async with NexusClient(api_key) as client:
            await client.abstain_mod(game.domain_name, mod_id, version=mod_version)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Nexus API error: {e}") from e

    dl = _get_or_create_download(session, game.id, mod_id, game.domain_name)  # type: ignore[arg-type]
    dl.is_endorsed = False
    session.commit()
    return ModActionResult(success=True, is_endorsed=False)


@router.post("/{game_name}/mods/{mod_id}/track", response_model=ModActionResult)
async def track_mod(
    game_name: str, mod_id: int, session: Session = Depends(get_session)
) -> ModActionResult:
    game = get_game_or_404(game_name, session)
    api_key = get_setting(session, "nexus_api_key")
    if not api_key:
        raise HTTPException(400, "Nexus API key not configured")

    from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError

    try:
        async with NexusClient(api_key) as client:
            await client.track_mod(game.domain_name, mod_id)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Nexus API error: {e}") from e

    dl = _get_or_create_download(session, game.id, mod_id, game.domain_name)  # type: ignore[arg-type]
    dl.is_tracked = True
    session.commit()
    return ModActionResult(success=True, is_tracked=True)


@router.delete("/{game_name}/mods/{mod_id}/track", response_model=ModActionResult)
async def untrack_mod(
    game_name: str, mod_id: int, session: Session = Depends(get_session)
) -> ModActionResult:
    game = get_game_or_404(game_name, session)
    api_key = get_setting(session, "nexus_api_key")
    if not api_key:
        raise HTTPException(400, "Nexus API key not configured")

    from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError

    try:
        async with NexusClient(api_key) as client:
            await client.untrack_mod(game.domain_name, mod_id)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Nexus API error: {e}") from e

    dl = _get_or_create_download(session, game.id, mod_id, game.domain_name)  # type: ignore[arg-type]
    dl.is_tracked = False
    session.commit()
    return ModActionResult(success=True, is_tracked=False)


@router.post("/sso/start", response_model=SSOStartResult)
async def sso_start() -> SSOStartResult:
    """Start a Nexus Mods SSO session."""
    from rippermod_manager.services.sso_service import start_sso

    try:
        session_uuid, authorize_url = await start_sso()
        return SSOStartResult(uuid=session_uuid, authorize_url=authorize_url)
    except RuntimeError:
        raise HTTPException(502, "Failed to connect to Nexus Mods SSO service") from None


@router.get("/sso/poll/{session_uuid}", response_model=SSOPollResult)
async def sso_poll(session_uuid: str, session: Session = Depends(get_session)) -> SSOPollResult:
    """Poll an SSO session for completion."""
    from rippermod_manager.services.sso_service import poll_sso

    sso = poll_sso(session_uuid)
    if sso is None:
        raise HTTPException(404, "SSO session not found or expired")

    if sso.status.value == "success" and sso.api_key and not sso.result_persisted:
        from rippermod_manager.services.settings_helpers import set_setting

        set_setting(session, "nexus_api_key", sso.api_key)

        if sso.result and sso.result.username:
            set_setting(session, "nexus_username", sso.result.username)
            set_setting(session, "nexus_is_premium", str(sso.result.is_premium).lower())

        session.commit()
        sso.result_persisted = True

    return SSOPollResult(
        status=sso.status.value,
        result=sso.result,
        error=sso.error,
    )


@router.delete("/sso/{session_uuid}")
async def sso_cancel(session_uuid: str) -> dict[str, bool]:
    """Cancel an active SSO session."""
    from rippermod_manager.services.sso_service import cancel_sso

    cancelled = cancel_sso(session_uuid)
    if not cancelled:
        raise HTTPException(404, "SSO session not found")
    return {"cancelled": True}
