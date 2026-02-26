import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.nexus import NexusDownload, NexusModFile, NexusModMeta
from rippermod_manager.nexus.client import NexusClient
from rippermod_manager.schemas.nexus import NexusSyncResult

logger = logging.getLogger(__name__)


async def sync_nexus_history(game: Game, api_key: str, session: Session) -> NexusSyncResult:
    async with NexusClient(api_key) as client:
        tracked_ids: set[int] = set()
        endorsed_ids: set[int] = set()

        tracked = await client.get_tracked_mods()
        for item in tracked:
            if item.get("domain_name") == game.domain_name:
                tracked_ids.add(item["mod_id"])

        endorsements = await client.get_endorsements()
        for item in endorsements:
            if item.get("domain_name") == game.domain_name:
                endorsed_ids.add(item["mod_id"])

        all_mod_ids = tracked_ids | endorsed_ids

        # Reset flags for all existing downloads of this game
        existing_all = session.exec(
            select(NexusDownload).where(NexusDownload.game_id == game.id)
        ).all()
        for dl in existing_all:
            dl.is_tracked = dl.nexus_mod_id in tracked_ids
            dl.is_endorsed = dl.nexus_mod_id in endorsed_ids

        for mod_id in all_mod_ids:
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
                    is_tracked=mod_id in tracked_ids,
                    is_endorsed=mod_id in endorsed_ids,
                )
                session.add(dl)
            else:
                existing_dl.mod_name = info.get("name", existing_dl.mod_name)
                # NOTE: do NOT overwrite version — preserves discovery-time snapshot
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
                    picture_url=info.get("picture_url", ""),
                )
                ts = info.get("updated_timestamp")
                if ts:
                    meta.updated_at = datetime.fromtimestamp(ts, tz=UTC)
                session.add(meta)
            else:
                existing_meta.name = info.get("name", existing_meta.name)
                existing_meta.summary = info.get("summary", existing_meta.summary)
                existing_meta.version = info.get("version", existing_meta.version)
                existing_meta.author = info.get("author", existing_meta.author)
                existing_meta.endorsement_count = info.get(
                    "endorsement_count", existing_meta.endorsement_count
                )
                existing_meta.picture_url = info.get("picture_url", existing_meta.picture_url)
                ts = info.get("updated_timestamp")
                if ts:
                    existing_meta.updated_at = datetime.fromtimestamp(ts, tz=UTC)

        # Fetch file lists for endorsed/tracked mods
        for mod_id in all_mod_ids:
            if client.hourly_remaining is not None and client.hourly_remaining < 10:
                logger.warning(
                    "Rate limit low (%d remaining), stopping file list fetch",
                    client.hourly_remaining,
                )
                break
            try:
                files_resp = await client.get_mod_files(
                    game.domain_name,
                    mod_id,
                    category="main,update,optional,miscellaneous",
                )
            except Exception:
                logger.warning("Failed to fetch files for %s/%d", game.domain_name, mod_id)
                continue

            existing_file_ids = {
                row.file_id
                for row in session.exec(
                    select(NexusModFile).where(NexusModFile.nexus_mod_id == mod_id)
                ).all()
            }

            for f in files_resp.get("files", []):
                fid = f.get("file_id")
                if not fid or fid in existing_file_ids:
                    continue
                session.add(
                    NexusModFile(
                        nexus_mod_id=mod_id,
                        file_id=fid,
                        file_name=f.get("file_name", ""),
                        version=f.get("version", ""),
                        category_id=f.get("category_id"),
                        uploaded_timestamp=f.get("uploaded_timestamp"),
                        file_size=f.get("size_in_bytes") or f.get("file_size", 0),
                        content_preview_link=f.get("content_preview_link"),
                        description=f.get("description"),
                    )
                )

            # Mark files as up-to-date so mod_detail skips redundant re-fetch
            sync_meta = session.exec(
                select(NexusModMeta).where(NexusModMeta.nexus_mod_id == mod_id)
            ).first()
            if sync_meta:
                sync_meta.files_updated_at = sync_meta.updated_at

        session.commit()

    total = session.exec(select(NexusDownload).where(NexusDownload.game_id == game.id)).all()

    try:
        from rippermod_manager.vector.indexer import index_nexus_metadata

        index_nexus_metadata(game.id)
        logger.info("Auto-indexed Nexus metadata into vector store after sync")
    except Exception:
        logger.warning("Failed to auto-index after Nexus sync", exc_info=True)

    return NexusSyncResult(
        tracked_mods=len(tracked_ids),
        endorsed_mods=len(endorsed_ids),
        total_stored=len(total),
    )
