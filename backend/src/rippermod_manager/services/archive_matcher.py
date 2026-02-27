"""Tier 2: MD5 hash matching for mod archives.

Computes MD5 hashes of downloaded archives and looks them up via the Nexus
v1 md5_search endpoint to identify exact mod+file matches.
"""

import hashlib
import logging
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import ArchiveNexusLink
from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError
from rippermod_manager.schemas.mod import ArchiveMatchResult
from rippermod_manager.services.install_service import list_available_archives
from rippermod_manager.services.nexus_helpers import upsert_nexus_mod
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
    """Compute MD5 hashes of downloaded archives and match via Nexus API."""
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

    on_progress("md5", f"Looking up {len(archive_hashes)} hashes on Nexus...", 93)

    matched = 0
    unmatched = 0

    async with NexusClient(api_key) as client:
        for i, (archive_path, md5) in enumerate(archive_hashes):
            # Rate limit safety
            if client.hourly_remaining is not None and client.hourly_remaining < 5:
                remaining = len(archive_hashes) - i
                on_progress("md5", f"Rate limit low, skipping {remaining} lookups", 95)
                logger.warning(
                    "Hourly rate limit low (%d), stopping MD5 matching",
                    client.hourly_remaining,
                )
                unmatched += remaining
                break

            try:
                results = await client.md5_search(game.domain_name, md5)
            except NexusRateLimitError:
                remaining = len(archive_hashes) - i
                on_progress("md5", f"Rate limited, skipping {remaining} lookups", 95)
                unmatched += remaining
                break
            except Exception:
                logger.warning("MD5 search failed for %s", archive_path.name)
                unmatched += 1
                continue

            if not results:
                unmatched += 1
                continue

            # md5_search returns a list of {mod, file_details} objects
            hit = results[0]
            mod_info = hit.get("mod", {})
            file_info = hit.get("file_details", {})
            mod_id = mod_info.get("mod_id")

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
            pct = 93 + int((i + 1) / len(archive_hashes) * 2)  # 93-95%
            mod_name = mod_info.get("name", "")
            on_progress("md5", f"Matched: {mod_name or archive_path.name}", pct)

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
