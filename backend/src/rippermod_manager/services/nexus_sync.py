import asyncio
import logging

import httpx
from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.nexus import NexusDownload, NexusModFile, NexusModMeta
from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
from rippermod_manager.schemas.nexus import NexusSyncResult
from rippermod_manager.services.nexus_helpers import (
    extract_dlc_requirements,
    graphql_file_to_rest_file,
    graphql_mod_to_rest_info,
    store_uid_from_gql,
    upsert_mod_requirements,
    upsert_nexus_mod,
)

logger = logging.getLogger(__name__)


async def sync_nexus_history(game: Game, api_key: str, session: Session) -> NexusSyncResult:
    async with NexusClient(api_key) as rest, NexusGraphQLClient(api_key) as gql:
        tracked_ids: set[int] = set()
        endorsed_ids: set[int] = set()

        # REST-only: get_tracked_mods + get_endorsements (no GQL list equivalent)
        tracked = await rest.get_tracked_mods()
        for item in tracked:
            if item.get("domain_name") == game.domain_name:
                tracked_ids.add(item["mod_id"])

        endorsements = await rest.get_endorsements()
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

        # GraphQL: batch fetch mod info instead of N sequential REST calls
        batch_info: dict[int, dict] = {}
        if all_mod_ids:
            try:
                batch_result = await gql.batch_mods_by_domain(game.domain_name, sorted(all_mod_ids))
                for mod_id, gql_mod in batch_result.items():
                    info = graphql_mod_to_rest_info(gql_mod)
                    batch_info[mod_id] = info
                    # Store UID
                    if gql_mod.get("uid"):
                        store_uid_from_gql(session, mod_id, gql_mod["uid"])
                    # Store mod requirements (forward + reverse + DLC)
                    mod_reqs = gql_mod.get("modRequirements") or {}
                    nexus_reqs = (mod_reqs.get("nexusRequirements") or {}).get("nodes") or []
                    reverse_reqs = (mod_reqs.get("modsRequiringThisMod") or {}).get("nodes") or []
                    dlc_reqs = extract_dlc_requirements(gql_mod)
                    if nexus_reqs or reverse_reqs or dlc_reqs:
                        upsert_mod_requirements(
                            session,
                            mod_id,
                            nexus_reqs,
                            reverse_requirements=reverse_reqs,
                            dlc_requirements=dlc_reqs,
                        )
            except NexusRateLimitError:
                logger.warning("Rate limited during batch mod fetch in sync")
            except httpx.HTTPError:
                logger.warning("Batch mod fetch failed in sync", exc_info=True)

        for mod_id in all_mod_ids:
            info = batch_info.get(mod_id)
            if not info:
                logger.debug("No batch info for mod %d (likely deleted/hidden), skipping", mod_id)
                continue

            upsert_nexus_mod(
                session,
                game.id,  # type: ignore[arg-type]
                game.domain_name,
                mod_id,
                info,
            )

            # Set tracking/endorsement flags on the download record
            dl_record = session.exec(
                select(NexusDownload).where(
                    NexusDownload.game_id == game.id,
                    NexusDownload.nexus_mod_id == mod_id,
                )
            ).first()
            if dl_record:
                dl_record.is_tracked = mod_id in tracked_ids
                dl_record.is_endorsed = mod_id in endorsed_ids

        # Parallel file list fetching for endorsed/tracked mods
        sem = asyncio.Semaphore(5)
        files_map: dict[int, list[dict]] = {}
        rate_limited = False

        async def _fetch_files(mid: int) -> None:
            nonlocal rate_limited
            if rate_limited:
                return
            async with sem:
                try:
                    gql_files = await gql.get_mod_files(game.domain_name, mid)
                    files_map[mid] = [graphql_file_to_rest_file(gf) for gf in gql_files]
                except NexusRateLimitError:
                    rate_limited = True
                    logger.warning("Rate limited fetching files, stopping file sync")
                except httpx.HTTPError:
                    logger.warning("Failed to fetch files for %s/%d", game.domain_name, mid)

        resolved_mod_ids = set(batch_info.keys())
        if resolved_mod_ids:
            await asyncio.gather(*[_fetch_files(mid) for mid in resolved_mod_ids])

        for mod_id, fetched_files in files_map.items():
            existing_file_ids = {
                row.file_id
                for row in session.exec(
                    select(NexusModFile).where(NexusModFile.nexus_mod_id == mod_id)
                ).all()
            }

            for f in fetched_files:
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
                        file_size=f.get("size_in_bytes") or 0,
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
