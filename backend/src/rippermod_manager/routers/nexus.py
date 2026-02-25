from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game
from rippermod_manager.models.settings import AppSetting

if TYPE_CHECKING:
    from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.nexus import (
    ModActionResult,
    ModDetailOut,
    NexusDownloadBrief,
    NexusModEnrichedOut,
    NexusModFileOut,
    NexusSyncResult,
    SSOPollResult,
    SSOStartResult,
)
from rippermod_manager.services.settings_helpers import get_setting

router = APIRouter(prefix="/nexus", tags=["nexus"])


@router.post("/sync-history/{game_name}", response_model=NexusSyncResult)
async def sync_history(game_name: str, session: Session = Depends(get_session)) -> NexusSyncResult:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")

    key_setting = session.exec(select(AppSetting).where(AppSetting.key == "nexus_api_key")).first()
    if not key_setting or not key_setting.value:
        raise HTTPException(400, "Nexus API key not configured")

    from rippermod_manager.services.nexus_sync import sync_nexus_history

    return await sync_nexus_history(game, key_setting.value, session)


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
    from rippermod_manager.models.nexus import NexusModFile, NexusModMeta
    from rippermod_manager.nexus.client import NexusClient
    from rippermod_manager.services.nexus_helpers import upsert_nexus_mod

    meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()

    key_setting = session.exec(select(AppSetting).where(AppSetting.key == "nexus_api_key")).first()
    api_key = key_setting.value if key_setting else ""

    if not meta or not meta.description:
        if not api_key:
            raise HTTPException(404, "Mod metadata not found and no API key configured")
        async with NexusClient(api_key) as client:
            info = await client.get_mod_info(game_domain, mod_id)
        game = session.exec(select(Game).where(Game.domain_name == game_domain)).first()
        if not game:
            raise HTTPException(404, f"Game domain '{game_domain}' not found")
        game_id = game.id
        upsert_nexus_mod(session, game_id, game_domain, mod_id, info)
        session.commit()
        meta = session.exec(select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)).first()

    if not meta:
        raise HTTPException(404, "Mod metadata not found")

    changelogs: dict[str, list[str]] = {}
    if api_key:
        try:
            async with NexusClient(api_key) as client:
                changelogs = await client.get_changelogs(game_domain, mod_id)
        except Exception:
            pass

    files = session.exec(select(NexusModFile).where(NexusModFile.nexus_mod_id == mod_id)).all()

    from rippermod_manager.models.nexus import NexusDownload

    dl = session.exec(select(NexusDownload).where(NexusDownload.nexus_mod_id == mod_id)).first()

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
        category=meta.category,
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
            )
            for f in files
        ],
        is_tracked=dl.is_tracked if dl else False,
        is_endorsed=dl.is_endorsed if dl else False,
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

    from httpx import HTTPStatusError

    from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError

    try:
        async with NexusClient(api_key) as client:
            await client.endorse_mod(game.domain_name, mod_id)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Nexus API error: {e.response.text}") from e

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

    from httpx import HTTPStatusError

    from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError

    try:
        async with NexusClient(api_key) as client:
            await client.abstain_mod(game.domain_name, mod_id)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Nexus API error: {e.response.text}") from e

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

    from httpx import HTTPStatusError

    from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError

    try:
        async with NexusClient(api_key) as client:
            await client.track_mod(game.domain_name, mod_id)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Nexus API error: {e.response.text}") from e

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

    from httpx import HTTPStatusError

    from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError

    try:
        async with NexusClient(api_key) as client:
            await client.untrack_mod(game.domain_name, mod_id)
    except NexusRateLimitError as e:
        raise HTTPException(429, f"Rate limited: {e}") from e
    except HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Nexus API error: {e.response.text}") from e

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
        setting = session.exec(select(AppSetting).where(AppSetting.key == "nexus_api_key")).first()
        if setting:
            setting.value = sso.api_key
        else:
            setting = AppSetting(key="nexus_api_key", value=sso.api_key)
            session.add(setting)

        if sso.result and sso.result.username:
            for k, v in [
                ("nexus_username", sso.result.username),
                ("nexus_is_premium", str(sso.result.is_premium).lower()),
            ]:
                row = session.exec(select(AppSetting).where(AppSetting.key == k)).first()
                if row:
                    row.value = v
                else:
                    session.add(AppSetting(key=k, value=v))

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
