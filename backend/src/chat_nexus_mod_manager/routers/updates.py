from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.models.settings import AppSetting

router = APIRouter(prefix="/games/{game_name}/updates", tags=["updates"])


class ModUpdate(BaseModel):
    mod_group_id: int
    display_name: str
    local_version: str
    nexus_version: str
    nexus_mod_id: int
    nexus_url: str
    author: str


class UpdateCheckResult(BaseModel):
    total_checked: int
    updates_available: int
    updates: list[ModUpdate]


def _get_game(game_name: str, session: Session) -> Game:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")
    return game


@router.get("/", response_model=UpdateCheckResult)
def list_updates(
    game_name: str, session: Session = Depends(get_session)
) -> UpdateCheckResult:
    game = _get_game(game_name, session)

    correlations = session.exec(
        select(ModNexusCorrelation, ModGroup, NexusDownload)
        .join(ModGroup, ModNexusCorrelation.mod_group_id == ModGroup.id)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .where(ModGroup.game_id == game.id)
    ).all()

    updates: list[ModUpdate] = []
    for _corr, group, download in correlations:
        meta = session.exec(
            select(NexusModMeta).where(
                NexusModMeta.nexus_mod_id == download.nexus_mod_id
            )
        ).first()
        if meta and meta.version and meta.version != download.version:
            updates.append(
                ModUpdate(
                    mod_group_id=group.id,  # type: ignore[arg-type]
                    display_name=group.display_name,
                    local_version=download.version,
                    nexus_version=meta.version,
                    nexus_mod_id=download.nexus_mod_id,
                    nexus_url=download.nexus_url,
                    author=meta.author,
                )
            )

    return UpdateCheckResult(
        total_checked=len(correlations),
        updates_available=len(updates),
        updates=updates,
    )


@router.post("/check", response_model=UpdateCheckResult)
async def check_updates(
    game_name: str, session: Session = Depends(get_session)
) -> UpdateCheckResult:
    game = _get_game(game_name, session)

    key_setting = session.exec(
        select(AppSetting).where(AppSetting.key == "nexus_api_key")
    ).first()

    if key_setting and key_setting.value:
        from chat_nexus_mod_manager.nexus.client import NexusClient

        async with NexusClient(key_setting.value) as client:
            updated_mods = await client.get_updated_mods(game.domain_name, "1w")
            for mod_data in updated_mods:
                nexus_mod_id = mod_data.get("mod_id")
                if nexus_mod_id:
                    meta = session.exec(
                        select(NexusModMeta).where(
                            NexusModMeta.nexus_mod_id == nexus_mod_id
                        )
                    ).first()
                    if meta:
                        latest = mod_data.get("latest_file_update") or mod_data.get(
                            "latest_mod_activity"
                        )
                        if latest:
                            info = await client.get_mod_info(
                                game.domain_name, nexus_mod_id
                            )
                            if info:
                                meta.version = info.get("version", meta.version)
                                meta.updated_at = info.get("updated_timestamp")
                            session.add(meta)
            session.commit()

    return list_updates(game_name, session)
