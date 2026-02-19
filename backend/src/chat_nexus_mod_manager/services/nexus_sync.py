import logging

from sqlmodel import Session, select

from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.nexus.client import NexusClient
from chat_nexus_mod_manager.schemas.nexus import NexusSyncResult

logger = logging.getLogger(__name__)


async def sync_nexus_history(
    game: Game, api_key: str, session: Session
) -> NexusSyncResult:
    tracked_count = 0
    endorsed_count = 0

    async with NexusClient(api_key) as client:
        mod_ids: set[int] = set()

        tracked = await client.get_tracked_mods()
        for item in tracked:
            if item.get("domain_name") == game.domain_name:
                mod_ids.add(item["mod_id"])
                tracked_count += 1

        endorsements = await client.get_endorsements()
        for item in endorsements:
            if item.get("domain_name") == game.domain_name:
                mod_ids.add(item["mod_id"])
                endorsed_count += 1

        for mod_id in mod_ids:
            try:
                info = await client.get_mod_info(game.domain_name, mod_id)
            except Exception:
                logger.warning("Failed to fetch mod info for %s/%d", game.domain_name, mod_id)
                continue

            existing_dl = session.exec(
                select(NexusDownload).where(
                    NexusDownload.game_id == game.id,
                    NexusDownload.nexus_mod_id == mod_id,
                )
            ).first()

            nexus_url = f"https://www.nexusmods.com/{game.domain_name}/mods/{mod_id}"

            if not existing_dl:
                dl = NexusDownload(
                    game_id=game.id,  # type: ignore[arg-type]
                    nexus_mod_id=mod_id,
                    mod_name=info.get("name", ""),
                    version=info.get("version", ""),
                    category=info.get("category_id", ""),
                    nexus_url=nexus_url,
                )
                session.add(dl)
            else:
                existing_dl.mod_name = info.get("name", existing_dl.mod_name)
                existing_dl.version = info.get("version", existing_dl.version)
                existing_dl.nexus_url = nexus_url

            existing_meta = session.exec(
                select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)
            ).first()

            if not existing_meta:
                meta = NexusModMeta(
                    nexus_mod_id=mod_id,
                    game_domain=game.domain_name,
                    name=info.get("name", ""),
                    summary=info.get("summary", ""),
                    author=info.get("author", ""),
                    version=info.get("version", ""),
                    endorsement_count=info.get("endorsement_count", 0),
                    category=str(info.get("category_id", "")),
                )
                session.add(meta)
            else:
                existing_meta.name = info.get("name", existing_meta.name)
                existing_meta.summary = info.get("summary", existing_meta.summary)
                existing_meta.version = info.get("version", existing_meta.version)
                existing_meta.author = info.get("author", existing_meta.author)
                existing_meta.endorsement_count = info.get(
                    "endorsement_count", existing_meta.endorsement_count
                )

        session.commit()

    total = session.exec(
        select(NexusDownload).where(NexusDownload.game_id == game.id)
    ).all()

    return NexusSyncResult(
        tracked_mods=tracked_count,
        endorsed_mods=endorsed_count,
        total_stored=len(total),
    )
