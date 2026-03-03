"""Tier 2: MD5 hash matching for mod archives.

Computes MD5 hashes of downloaded archives and looks them up via the Nexus
GraphQL v2 batch_file_hashes endpoint for efficient bulk matching.
"""

import hashlib
import logging
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import ArchiveNexusLink
from rippermod_manager.nexus.client import NexusRateLimitError
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
from rippermod_manager.schemas.mod import ArchiveMatchResult
from rippermod_manager.services.install_service import list_available_archives
from rippermod_manager.services.nexus_helpers import (
    graphql_hash_to_mod_info,
    store_uid_from_gql,
    upsert_nexus_mod,
)
from rippermod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)


def _compute_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def match_archives_by_md5(
    game: Game,
    api_key: str,
    session: Session,
    on_progress: ProgressCallback = noop_progress,
) -> ArchiveMatchResult:
    """Compute MD5 hashes of downloaded archives and batch-match via Nexus GraphQL."""
    archives = list_available_archives(game)

    if not archives:
        on_progress("md5", "No archives found", 95)
        return ArchiveMatchResult(archives_scanned=0, matched=0, unmatched=0)

    on_progress("md5", f"Hashing {len(archives)} archives...", 92)

    # Compute hashes for all archives
    archive_hashes: list[tuple[Path, str]] = []
    for i, archive_path in enumerate(archives):
        try:
            md5 = _compute_md5(archive_path)
            archive_hashes.append((archive_path, md5))
        except OSError:
            logger.warning("Could not hash archive: %s", archive_path)

        if (i + 1) % 10 == 0:
            pct = 92 + int((i + 1) / len(archives) * 1)  # 92-93%
            on_progress("md5", f"Hashed {i + 1}/{len(archives)} archives", pct)

    if not archive_hashes:
        return ArchiveMatchResult(archives_scanned=0, matched=0, unmatched=0)

    on_progress("md5", f"Looking up {len(archive_hashes)} hashes on Nexus...", 93)

    all_md5s = [md5 for _, md5 in archive_hashes]

    matched = 0
    unmatched = 0

    try:
        async with NexusGraphQLClient(api_key) as gql:
            hits = await gql.batch_file_hashes(all_md5s)

        # Build md5 → hit mapping (first hit per md5)
        md5_to_hit: dict[str, dict] = {}
        for hit in hits:
            md5 = hit.get("md5", "")
            if md5 and md5 not in md5_to_hit:
                md5_to_hit[md5] = hit

        for archive_path, md5 in archive_hashes:
            hit = md5_to_hit.get(md5)
            if not hit:
                unmatched += 1
                continue

            mod_info, file_info, mod_id = graphql_hash_to_mod_info(hit)

            if not mod_id:
                unmatched += 1
                continue

            file_name = file_info.get("file_name", archive_path.name)
            file_id = file_info.get("file_id")
            # Merge file-level version into mod info for upsert
            info = {**mod_info}
            if file_info.get("version"):
                info["version"] = file_info["version"]

            upsert_nexus_mod(
                session,
                game.id,  # type: ignore[arg-type]
                game.domain_name,
                mod_id,
                info,
                file_name=file_name,
                file_id=file_id,
            )

            # Store UID from GraphQL response
            mod_file = hit.get("modFile") or {}
            mod_data = mod_file.get("mod") or {}
            if mod_data.get("uid"):
                store_uid_from_gql(session, mod_id, mod_data["uid"])

            # Store local filename → mod_id so list_archives can surface it
            existing_link = session.exec(
                select(ArchiveNexusLink).where(
                    ArchiveNexusLink.game_id == game.id,
                    ArchiveNexusLink.filename == archive_path.name,
                )
            ).first()
            if existing_link:
                existing_link.nexus_mod_id = mod_id
            else:
                session.add(
                    ArchiveNexusLink(
                        game_id=game.id,  # type: ignore[arg-type]
                        filename=archive_path.name,
                        nexus_mod_id=mod_id,
                    )
                )

            matched += 1
            mod_name = mod_info.get("name", "")
            on_progress("md5", f"Matched: {mod_name or archive_path.name}", 94)

    except NexusRateLimitError:
        on_progress("md5", "Rate limited during batch hash lookup", 95)
        unmatched = len(archive_hashes) - matched
    except Exception:
        logger.warning("Batch MD5 search failed", exc_info=True)
        unmatched = len(archive_hashes) - matched

    session.commit()
    logger.info(
        "MD5 matching: scanned=%d, matched=%d, unmatched=%d",
        len(archive_hashes),
        matched,
        unmatched,
    )
    return ArchiveMatchResult(
        archives_scanned=len(archive_hashes),
        matched=matched,
        unmatched=unmatched,
    )
