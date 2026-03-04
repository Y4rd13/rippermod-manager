"""Tier 1.5: Reverse file lookup via Nexus modFileContents search.

For mods without an ID in filename (Tier 1 miss) and without an archive
(Tier 2 miss), search Nexus by distinctive internal file paths to find
the originating mod.
"""

import logging
from pathlib import PurePosixPath

import httpx
from sqlmodel import Session, select

from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.game import Game
from rippermod_manager.models.mod import ModFile, ModGroup
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.nexus.client import NexusRateLimitError
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
from rippermod_manager.schemas.mod import FileContentMatchResult
from rippermod_manager.services.nexus_helpers import upsert_nexus_mod
from rippermod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)

_GENERIC_NAMES = frozenset(
    {
        "mod.archive",
        "main.lua",
        "init.lua",
        "info.json",
        "readme.txt",
        "readme.md",
        "config.yaml",
        "config.json",
        "config.xml",
        "manifest.json",
        "metadata.json",
        "license.txt",
        "license.md",
        "changelog.txt",
        "changelog.md",
        "description.txt",
        "modinfo.xml",
    }
)

_MIN_FILENAME_LEN = 8
_CORRELATION_SCORE = 0.88


def _pick_distinctive_file(files: list[ModFile]) -> str | None:
    """Select the most distinctive filename from a group's files for search."""
    candidates: list[tuple[str, str]] = []  # (stem, filename)

    for f in files:
        name = PurePosixPath(f.filename).name.lower()
        stem = PurePosixPath(name).stem
        ext = PurePosixPath(name).suffix

        if name in _GENERIC_NAMES:
            continue
        if len(stem) < _MIN_FILENAME_LEN:
            continue

        # Prefer .archive files (highly distinctive in Cyberpunk)
        priority = 0 if ext == ".archive" else 1
        candidates.append((f"{priority}_{stem}", stem))

    if not candidates:
        return None

    candidates.sort()
    return candidates[0][1]


async def match_by_file_contents(
    game: Game,
    api_key: str,
    session: Session,
    on_progress: ProgressCallback = noop_progress,
    max_searches: int = 15,
) -> FileContentMatchResult:
    """Search Nexus file contents to match unmatched mod groups."""
    # Get unmatched groups
    all_group_ids = set(
        session.exec(
            select(ModGroup.id).where(ModGroup.game_id == game.id)  # type: ignore[arg-type]
        ).all()
    )
    matched_group_ids = set(
        session.exec(
            select(ModNexusCorrelation.mod_group_id)
            .join(ModGroup, ModNexusCorrelation.mod_group_id == ModGroup.id)
            .where(ModGroup.game_id == game.id)
        ).all()
    )
    unmatched_ids = all_group_ids - matched_group_ids

    if not unmatched_ids:
        return FileContentMatchResult(groups_searched=0, matched=0, skipped_generic=0)

    unmatched_groups = session.exec(
        select(ModGroup).where(
            ModGroup.id.in_(unmatched_ids)  # type: ignore[union-attr]
        )
    ).all()

    # Build group -> distinctive file map
    search_candidates: list[tuple[ModGroup, str]] = []
    skipped_generic = 0

    for group in unmatched_groups:
        files = session.exec(select(ModFile).where(ModFile.mod_group_id == group.id)).all()
        distinctive = _pick_distinctive_file(files)
        if distinctive:
            search_candidates.append((group, distinctive))
        else:
            skipped_generic += 1

    if not search_candidates:
        return FileContentMatchResult(groups_searched=0, matched=0, skipped_generic=skipped_generic)

    # Limit searches
    search_candidates = search_candidates[:max_searches]

    matched = 0
    searches_done = 0

    try:
        async with NexusGraphQLClient(api_key) as gql:
            for i, (group, stem) in enumerate(search_candidates):
                try:
                    results = await gql.search_file_contents(
                        game.domain_name,
                        file_path_wildcard=f"*{stem}*",
                        count=5,
                    )
                except NexusRateLimitError:
                    on_progress("file-content", "Rate limited, stopping", 90)
                    logger.warning("Rate limited during file content search")
                    break
                except httpx.HTTPError:
                    logger.debug("File content search failed for '%s'", stem)
                    continue

                searches_done += 1

                if not results:
                    continue

                # Check if all results point to the same mod
                mod_ids = set()
                for node in results:
                    mid = node.get("modId")
                    if mid:
                        mod_ids.add(mid)

                if len(mod_ids) != 1:
                    continue

                nexus_mod_id = mod_ids.pop()

                # Skip if already correlated
                existing_dl = session.exec(
                    select(NexusDownload).where(
                        NexusDownload.game_id == game.id,
                        NexusDownload.nexus_mod_id == nexus_mod_id,
                    )
                ).first()

                if not existing_dl:
                    # Fetch mod info to create NexusDownload
                    try:
                        gql_mod = await gql.get_mod(game.domain_name, nexus_mod_id)
                        from rippermod_manager.services.nexus_helpers import (
                            graphql_mod_to_rest_info,
                        )

                        info = graphql_mod_to_rest_info(gql_mod)
                        existing_dl = upsert_nexus_mod(
                            session,
                            game.id,  # type: ignore[arg-type]
                            game.domain_name,
                            nexus_mod_id,
                            info,
                        )
                        session.flush()
                    except (NexusRateLimitError, httpx.HTTPError):
                        logger.debug("Could not fetch mod %d for file content match", nexus_mod_id)
                        continue

                # Check this group doesn't already have a correlation from a prior phase
                existing_group_corr = session.exec(
                    select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == group.id)
                ).first()
                if existing_group_corr:
                    continue

                # Check this nexus mod isn't already correlated to another group
                existing_corr = session.exec(
                    select(ModNexusCorrelation).where(
                        ModNexusCorrelation.nexus_download_id == existing_dl.id
                    )
                ).first()
                if existing_corr:
                    continue

                mod_name = existing_dl.mod_name
                corr = ModNexusCorrelation(
                    mod_group_id=group.id,  # type: ignore[arg-type]
                    nexus_download_id=existing_dl.id,  # type: ignore[arg-type]
                    score=_CORRELATION_SCORE,
                    method="file_content",
                    reasoning=(
                        f"File content search for '{stem}' matched "
                        f"mod {nexus_mod_id} ('{mod_name}')"
                    ),
                )
                session.add(corr)
                matched += 1

                logger.info(
                    "File content match: '%s' -> mod %d ('%s') via '%s'",
                    group.display_name,
                    nexus_mod_id,
                    mod_name,
                    stem,
                )

                pct = 88 + int((i + 1) / len(search_candidates) * 2)  # 88-90%
                on_progress("file-content", f"Matched: {mod_name}", pct)

    except NexusRateLimitError:
        logger.warning("Rate limited during file content matching")
    except httpx.HTTPError:
        logger.warning("File content matching failed", exc_info=True)

    if matched:
        session.commit()

    return FileContentMatchResult(
        groups_searched=searches_done, matched=matched, skipped_generic=skipped_generic
    )
