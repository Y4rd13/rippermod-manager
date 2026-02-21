"""Tier 1: Filename ID extraction + Nexus API enrichment.

Parses Nexus mod IDs from local filenames and fetches mod info from the API
to expand the matching pool before fuzzy correlation runs.
"""

import logging

from sqlmodel import Session, select

from chat_nexus_mod_manager.matching.filename_parser import parse_mod_filename
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModFile
from chat_nexus_mod_manager.models.nexus import NexusDownload
from chat_nexus_mod_manager.nexus.client import NexusClient, NexusRateLimitError
from chat_nexus_mod_manager.schemas.mod import EnrichResult
from chat_nexus_mod_manager.services.nexus_helpers import (
    match_local_to_nexus_file,
    upsert_nexus_mod,
)
from chat_nexus_mod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)


async def enrich_from_filename_ids(
    game: Game,
    api_key: str,
    session: Session,
    on_progress: ProgressCallback = noop_progress,
) -> EnrichResult:
    """Extract Nexus mod IDs from filenames and fetch mod info from the API."""
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

    async with NexusClient(api_key) as client:
        for i, mod_id in enumerate(sorted(new_ids)):
            # Rate limit safety: stop if running low
            if client.hourly_remaining is not None and client.hourly_remaining < 5:
                remaining = len(new_ids) - i
                on_progress("enrich", f"Rate limit low, skipping {remaining} mods", 91)
                logger.warning(
                    "Hourly rate limit low (%d), stopping enrichment", client.hourly_remaining
                )
                break

            try:
                info = await client.get_mod_info(game.domain_name, mod_id)
            except NexusRateLimitError:
                remaining = len(new_ids) - i
                on_progress("enrich", f"Rate limited, skipping {remaining} mods", 91)
                logger.warning("Rate limited during enrichment, stopping")
                break
            except Exception:
                logger.warning("Failed to fetch mod info for %s/%d", game.domain_name, mod_id)
                ids_failed += 1
                continue

            # Resolve file_id by matching local filenames against Nexus file list
            file_name_resolved = ""
            file_id_resolved: int | None = None
            local_entries = id_to_filenames.get(mod_id, [])
            if local_entries:
                try:
                    files_resp = await client.get_mod_files(game.domain_name, mod_id)
                    nexus_files = files_resp.get("files", [])
                    for local_fn, local_ver, local_ts in local_entries:
                        matched = match_local_to_nexus_file(
                            local_fn,
                            nexus_files,
                            parsed_version=local_ver,
                            parsed_timestamp=local_ts,
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
                info,  # type: ignore[arg-type]
                file_name=file_name_resolved,
                file_id=file_id_resolved,
            )

            ids_new += 1
            pct = 86 + int((i + 1) / len(new_ids) * 5)  # 86-91%
            on_progress("enrich", f"Fetched: {info.get('name', f'mod {mod_id}')}", pct)

    session.commit()
    logger.info("Enrichment: found=%d, new=%d, failed=%d", ids_found, ids_new, ids_failed)
    return EnrichResult(ids_found=ids_found, ids_new=ids_new, ids_failed=ids_failed)
