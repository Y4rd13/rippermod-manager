import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game

if TYPE_CHECKING:
    from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.nexus import (
    DlcRequirementOut,
    ModActionResult,
    ModRequirementOut,
    ModSummaryOut,
    NexusDownloadBrief,
    NexusModEnrichedOut,
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


async def _fetch_requirements(
    api_key: str, game_domain: str, mod_id: int, session: Session
) -> None:
    """Fetch mod requirements from GraphQL and store them."""
    from rippermod_manager.models.nexus import NexusModMeta
    from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
    from rippermod_manager.services.nexus_helpers import (
        extract_dlc_requirements,
        upsert_mod_requirements,
    )

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
    meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()
    if meta:
        meta.requirements_fetched_at = datetime.now(UTC)
    session.commit()


@router.get("/mods/{mod_id}/summary", response_model=ModSummaryOut)
async def mod_summary(mod_id: int, session: Session = Depends(get_session)) -> ModSummaryOut:
    """Lightweight mod summary for management UI (no description, changelogs, or file lists)."""
    from rippermod_manager.models.nexus import NexusDownload, NexusModMeta, NexusModRequirement

    meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()

    if not meta:
        api_key = get_setting(session, "nexus_api_key") or ""
        if not api_key:
            raise HTTPException(404, "Mod metadata not found and no API key configured")

        from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
        from rippermod_manager.services.nexus_helpers import (
            graphql_mod_to_rest_info,
            store_uid_from_gql,
            upsert_nexus_mod,
        )

        game = session.exec(select(Game)).first()
        if not game:
            raise HTTPException(404, "No game configured")
        game_domain = game.domain_name

        async with NexusGraphQLClient(api_key) as gql:
            gql_mod = await gql.get_mod(game_domain, mod_id)
        info = graphql_mod_to_rest_info(gql_mod)
        upsert_nexus_mod(session, game.id, game_domain, mod_id, info)
        if gql_mod.get("uid"):
            store_uid_from_gql(session, mod_id, gql_mod["uid"])

        await _fetch_requirements(api_key, game_domain, mod_id, session)
        meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()

    if not meta:
        raise HTTPException(404, "Mod metadata not found")

    # Resolve category
    category_name = meta.category
    try:
        cat_id = int(meta.category)
        from rippermod_manager.services.nexus_helpers import get_cached_game_categories

        categories = get_cached_game_categories(meta.game_domain, session)
        if categories and cat_id in categories:
            category_name = categories[cat_id]
    except (ValueError, TypeError):
        pass

    # Get tracked/endorsed state
    dl = session.exec(select(NexusDownload).where(NexusDownload.nexus_mod_id == mod_id)).first()

    # Backfill requirements if needed
    req_rows = session.exec(
        select(NexusModRequirement).where(NexusModRequirement.nexus_mod_id == mod_id)
    ).all()
    if not req_rows and not meta.requirements_fetched_at:
        api_key = get_setting(session, "nexus_api_key") or ""
        if api_key:
            try:
                await _fetch_requirements(api_key, meta.game_domain, mod_id, session)
                req_rows = session.exec(
                    select(NexusModRequirement).where(NexusModRequirement.nexus_mod_id == mod_id)
                ).all()
            except httpx.HTTPError:
                logger.debug("Failed to backfill requirements for mod %d", mod_id, exc_info=True)

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

    nexus_url = f"https://www.nexusmods.com/{meta.game_domain}/mods/{mod_id}"

    return ModSummaryOut(
        nexus_mod_id=meta.nexus_mod_id,
        name=meta.name,
        author=meta.author,
        version=meta.version,
        category=category_name,
        nexus_url=nexus_url,
        is_tracked=dl.is_tracked if dl else False,
        is_endorsed=dl.is_endorsed if dl else False,
        requirements=requirements,
        dlc_requirements=dlc_requirements,
    )


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
