from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.settings import AppSetting
from chat_nexus_mod_manager.schemas.nexus import (
    NexusDownloadOut,
    NexusKeyResult,
    NexusKeyValidation,
    NexusSyncResult,
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


@router.get("/downloads/{game_name}", response_model=list[NexusDownloadOut])
def list_downloads(
    game_name: str, session: Session = Depends(get_session)
) -> list[NexusDownloadOut]:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")

    from chat_nexus_mod_manager.models.nexus import NexusDownload

    downloads = session.exec(select(NexusDownload).where(NexusDownload.game_id == game.id)).all()
    return [
        NexusDownloadOut(
            id=d.id,  # type: ignore[arg-type]
            nexus_mod_id=d.nexus_mod_id,
            mod_name=d.mod_name,
            file_name=d.file_name,
            version=d.version,
            category=d.category,
            downloaded_at=d.downloaded_at,
            nexus_url=d.nexus_url,
        )
        for d in downloads
    ]
