"""Tier 1: Filename ID extraction + Nexus API enrichment.

Parses Nexus mod IDs from local filenames and fetches mod info from the API
to expand the matching pool before fuzzy correlation runs.

Uses GraphQL v2 batch_mods() for mod info (1 query per ~50 mods) and
per-mod get_mod_files() for file resolution.
"""

import logging

from sqlmodel import Session, select

from rippermod_manager.matching.filename_parser import parse_mod_filename
from rippermod_manager.models.game import Game
from rippermod_manager.models.mod import ModFile
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.nexus.client import NexusRateLimitError
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
from rippermod_manager.schemas.mod import EnrichResult
from rippermod_manager.services.nexus_helpers import (
    graphql_file_to_rest_file,
    graphql_mod_to_rest_info,
    match_local_to_nexus_file,
    store_uid_from_gql,
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
        on_progress("enrich", "No filename IDs found", 87)
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
    on_progress("enrich", f"Found {ids_found} IDs, {len(new_ids)} new", 86)

    if not new_ids:
        return EnrichResult(ids_found=ids_found, ids_new=0, ids_failed=0)

    ids_new = 0
    ids_failed = 0

    try:
        async with NexusGraphQLClient(api_key) as gql:
            # Batch fetch mod info (chunks of ~50 via aliases)
            on_progress("enrich", f"Batch-fetching {len(new_ids)} mod infos...", 87)
            try:
                batch_result = await gql.batch_mods(game.domain_name, sorted(new_ids))
            except NexusRateLimitError:
                on_progress("enrich", "Rate limited during batch fetch", 91)
                logger.warning("Rate limited during batch enrichment")
                return EnrichResult(ids_found=ids_found, ids_new=0, ids_failed=len(new_ids))

            for i, mod_id in enumerate(sorted(new_ids)):
                gql_mod = batch_result.get(mod_id)
                if not gql_mod:
                    ids_failed += 1
                    continue

                info = graphql_mod_to_rest_info(gql_mod)

                # Store UID
                if gql_mod.get("uid"):
                    store_uid_from_gql(session, mod_id, gql_mod["uid"])

                # Resolve file_id by matching local filenames against Nexus file list
                file_name_resolved = ""
                file_id_resolved: int | None = None
                local_entries = id_to_filenames.get(mod_id, [])
                if local_entries:
                    try:
                        gql_files = await gql.get_mod_files(game.domain_name, mod_id)
                        nexus_files = [graphql_file_to_rest_file(gf) for gf in gql_files]
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
                    except NexusRateLimitError:
                        logger.debug("Rate limited fetching files for mod %d", mod_id)
                    except Exception:
                        logger.debug("Could not fetch files for mod %d", mod_id)

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
                pct = 87 + int((i + 1) / len(new_ids) * 4)  # 87-91%
                on_progress("enrich", f"Fetched: {info.get('name', f'mod {mod_id}')}", pct)

    except NexusRateLimitError:
        on_progress("enrich", "Rate limited during enrichment", 91)
        logger.warning("Rate limited during enrichment")
    except Exception:
        logger.warning("Enrichment batch failed", exc_info=True)

    session.commit()
    logger.info("Enrichment: found=%d, new=%d, failed=%d", ids_found, ids_new, ids_failed)
    return EnrichResult(ids_found=ids_found, ids_new=ids_new, ids_failed=ids_failed)
