from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.settings import AppSetting
from chat_nexus_mod_manager.schemas.nexus import (
    NexusKeyResult,
    NexusKeyValidation,
    NexusModEnrichedOut,
    NexusSyncResult,
    SSOPollResult,
    SSOStartResult,
)

router = APIRouter(prefix="/nexus", tags=["nexus"])


@router.post("/validate", response_model=NexusKeyResult)
async def validate_key(data: NexusKeyValidation) -> NexusKeyResult:
    from chat_nexus_mod_manager.nexus.client import NexusClient

    async with NexusClient(data.api_key) as client:
        return await client.validate_key()


@router.post("/connect", response_model=NexusKeyResult)
async def connect_and_store(
    data: NexusKeyValidation, session: Session = Depends(get_session)
) -> NexusKeyResult:
    from chat_nexus_mod_manager.nexus.client import NexusClient

    async with NexusClient(data.api_key) as client:
        result = await client.validate_key()

    if result.valid:
        setting = session.exec(select(AppSetting).where(AppSetting.key == "nexus_api_key")).first()
        if setting:
            setting.value = data.api_key
        else:
            setting = AppSetting(key="nexus_api_key", value=data.api_key)
            session.add(setting)
        session.commit()

    return result


@router.post("/sync-history/{game_name}", response_model=NexusSyncResult)
async def sync_history(game_name: str, session: Session = Depends(get_session)) -> NexusSyncResult:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")

    key_setting = session.exec(select(AppSetting).where(AppSetting.key == "nexus_api_key")).first()
    if not key_setting or not key_setting.value:
        raise HTTPException(400, "Nexus API key not configured")

    from chat_nexus_mod_manager.services.nexus_sync import sync_nexus_history

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

    from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta

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


@router.post("/sso/start", response_model=SSOStartResult)
async def sso_start() -> SSOStartResult:
    """Start a Nexus Mods SSO session."""
    from chat_nexus_mod_manager.services.sso_service import start_sso

    try:
        session_uuid, authorize_url = await start_sso()
        return SSOStartResult(uuid=session_uuid, authorize_url=authorize_url)
    except RuntimeError:
        raise HTTPException(502, "Failed to connect to Nexus Mods SSO service") from None


@router.get("/sso/poll/{session_uuid}", response_model=SSOPollResult)
async def sso_poll(session_uuid: str, session: Session = Depends(get_session)) -> SSOPollResult:
    """Poll an SSO session for completion."""
    from chat_nexus_mod_manager.services.sso_service import poll_sso

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
    from chat_nexus_mod_manager.services.sso_service import cancel_sso

    cancelled = cancel_sso(session_uuid)
    if not cancelled:
        raise HTTPException(404, "SSO session not found")
    return {"cancelled": True}
