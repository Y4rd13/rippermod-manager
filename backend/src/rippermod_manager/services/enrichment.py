"""Tier 1: Filename ID extraction + Nexus API enrichment.

Parses Nexus mod IDs from local filenames and fetches mod info from the API
to expand the matching pool before fuzzy correlation runs.

Uses GraphQL v2 batch_mods_by_domain() for mod info and parallel
get_mod_files() for file resolution.
"""

import asyncio
import logging

import httpx
from sqlmodel import Session, select

from rippermod_manager.matching.filename_parser import parse_mod_filename
from rippermod_manager.models.game import Game
from rippermod_manager.models.mod import ModFile
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.nexus.client import NexusRateLimitError
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
from rippermod_manager.schemas.mod import EnrichResult
from rippermod_manager.services.nexus_helpers import (
    extract_dlc_requirements,
    graphql_file_to_rest_file,
    graphql_mod_to_rest_info,
    match_local_to_nexus_file,
    store_uid_from_gql,
    upsert_mod_requirements,
    upsert_nexus_mod,
)
from rippermod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)


async def enrich_from_filename_ids(
    game: Game,
    api_key: str,
    session: Session,
    on_progress: ProgressCallback = noop_progress,
) -> EnrichResult:
    """Extract Nexus mod IDs from filenames and batch-fetch mod info via GraphQL."""
    files = session.exec(select(ModFile).where(ModFile.mod_group_id.is_not(None))).all()  # type: ignore[union-attr]

    # Collect unique nexus mod IDs and map mod_id -> local filenames (with parsed data)
    candidate_ids: set[int] = set()
    id_to_filenames: dict[int, list[tuple[str, str | None, int | None]]] = {}
    for f in files:
        parsed = parse_mod_filename(f.filename)
        if parsed.nexus_mod_id:
            candidate_ids.add(parsed.nexus_mod_id)
            id_to_filenames.setdefault(parsed.nexus_mod_id, []).append(
                (f.filename, parsed.version, parsed.upload_timestamp)
            )

    if not candidate_ids:
        on_progress("enrich", "No filename IDs found", 85)
        return EnrichResult(ids_found=0, ids_new=0, ids_failed=0)

    # Filter out IDs already in the NexusDownload table for this game
    existing_ids_rows = session.exec(
        select(NexusDownload.nexus_mod_id).where(
            NexusDownload.game_id == game.id,
            NexusDownload.nexus_mod_id.in_(candidate_ids),  # type: ignore[union-attr]
        )
    ).all()
    existing_ids = set(existing_ids_rows)
    new_ids = candidate_ids - existing_ids

    ids_found = len(candidate_ids)
    on_progress("enrich", f"Found {ids_found} IDs, {len(new_ids)} new", 84)

    if not new_ids:
        return EnrichResult(ids_found=ids_found, ids_new=0, ids_failed=0)

    ids_new = 0
    ids_failed = 0

    try:
        async with NexusGraphQLClient(api_key) as gql:
            # Batch fetch mod info (chunks of ~50 via aliases)
            on_progress("enrich", f"Batch-fetching {len(new_ids)} mod infos...", 84)
            try:
                batch_result = await gql.batch_mods_by_domain(game.domain_name, sorted(new_ids))
            except NexusRateLimitError:
                on_progress("enrich", "Rate limited during batch fetch", 88)
                logger.warning("Rate limited during batch enrichment")
                return EnrichResult(ids_found=ids_found, ids_new=0, ids_failed=len(new_ids))

            # Process batch results: store metadata and requirements
            sorted_new = sorted(new_ids)
            mod_infos: dict[int, dict] = {}
            mods_needing_files: list[int] = []

            for mod_id in sorted_new:
                gql_mod = batch_result.get(mod_id)
                if not gql_mod:
                    ids_failed += 1
                    continue

                info = graphql_mod_to_rest_info(gql_mod)
                mod_infos[mod_id] = info

                if gql_mod.get("uid"):
                    store_uid_from_gql(session, mod_id, gql_mod["uid"])

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

                if id_to_filenames.get(mod_id):
                    mods_needing_files.append(mod_id)

            # Parallel file list fetching with semaphore
            sem = asyncio.Semaphore(5)
            files_map: dict[int, list[dict]] = {}

            async def _fetch_files(mid: int) -> None:
                async with sem:
                    try:
                        gql_files = await gql.get_mod_files(game.domain_name, mid)
                        files_map[mid] = [graphql_file_to_rest_file(gf) for gf in gql_files]
                    except NexusRateLimitError:
                        logger.debug("Rate limited fetching files for mod %d", mid)
                    except httpx.HTTPError:
                        logger.debug("Could not fetch files for mod %d", mid)

            if mods_needing_files:
                await asyncio.gather(*[_fetch_files(mid) for mid in mods_needing_files])

            # Resolve file IDs and upsert
            for i, mod_id in enumerate(sorted_new):
                info = mod_infos.get(mod_id)
                if not info:
                    continue

                file_name_resolved = ""
                file_id_resolved: int | None = None
                local_entries = id_to_filenames.get(mod_id, [])
                nexus_files = files_map.get(mod_id, [])

                if local_entries and nexus_files:
                    for local_fn, local_ver, local_ts in local_entries:
                        matched = match_local_to_nexus_file(
                            local_fn,
                            nexus_files,
                            parsed_version=local_ver,
                            parsed_timestamp=local_ts,
                            strict=True,
                        )
                        if matched:
                            file_name_resolved = matched.get("file_name", "")
                            file_id_resolved = matched.get("file_id")
                            break

                upsert_nexus_mod(
                    session,
                    game.id,
                    game.domain_name,
                    mod_id,
                    info,
                    file_name=file_name_resolved,
                    file_id=file_id_resolved,
                )

                ids_new += 1
                pct = 84 + int((i + 1) / len(sorted_new) * 4)  # 84-88%
                on_progress("enrich", f"Fetched: {info.get('name', f'mod {mod_id}')}", pct)

    except NexusRateLimitError:
        on_progress("enrich", "Rate limited during enrichment", 88)
        logger.warning("Rate limited during enrichment")
    except httpx.HTTPError:
        logger.warning("Enrichment batch failed", exc_info=True)

    session.commit()
    logger.info("Enrichment: found=%d, new=%d, failed=%d", ids_found, ids_new, ids_failed)
    return EnrichResult(ids_found=ids_found, ids_new=ids_new, ids_failed=ids_failed)
