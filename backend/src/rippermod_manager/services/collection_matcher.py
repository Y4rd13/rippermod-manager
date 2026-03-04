"""Match mods by detecting Nexus collections among correlated mods.

If 3+ already-correlated mods share a collection, fetch the collection's
mod list and match remaining unmatched groups against it.
"""

import logging

import httpx
from sqlmodel import Session, select

from rippermod_manager.matching.correlator import compute_name_score
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.game import Game
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.nexus.client import NexusRateLimitError
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient, NexusGraphQLError
from rippermod_manager.schemas.mod import RequirementMatchResult
from rippermod_manager.services.nexus_helpers import upsert_nexus_mod
from rippermod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)

_MIN_COLLECTION_OVERLAP = 3
_NAME_THRESHOLD = 0.55
_CORRELATION_SCORE = 0.85


async def match_by_collections(
    game: Game,
    api_key: str,
    session: Session,
    on_progress: ProgressCallback = noop_progress,
) -> RequirementMatchResult:
    """Detect collections and match unmatched groups against their mod lists."""
    # Get correlated nexus_mod_ids
    correlated = session.exec(
        select(NexusDownload.nexus_mod_id)
        .join(ModNexusCorrelation, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .where(NexusDownload.game_id == game.id)
    ).all()
    correlated_nexus_ids = set(correlated)

    if len(correlated_nexus_ids) < _MIN_COLLECTION_OVERLAP:
        return RequirementMatchResult(requirements_checked=0, matched=0)

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
        return RequirementMatchResult(requirements_checked=0, matched=0)

    unmatched_groups = session.exec(
        select(ModGroup).where(ModGroup.id.in_(unmatched_ids))  # type: ignore[union-attr]
    ).all()

    matched = 0
    collections_checked = 0

    try:
        async with NexusGraphQLClient(api_key) as gql:
            # Search top collections for this game
            try:
                collections = await gql.search_collections(game.domain_name, count=10)
            except (NexusRateLimitError, NexusGraphQLError, httpx.HTTPError):
                logger.warning("Failed to search collections", exc_info=True)
                return RequirementMatchResult(requirements_checked=0, matched=0)

            newly_matched_groups: set[int] = set()
            newly_matched_nexus_ids: set[int] = set()

            for coll in collections:
                slug = coll.get("slug", "")
                rev_info = coll.get("latestPublishedRevision") or {}
                rev_num = rev_info.get("revisionNumber")
                if not slug or not rev_num:
                    continue

                try:
                    revision = await gql.get_collection_revision(slug, rev_num, game.domain_name)
                except (NexusRateLimitError, NexusGraphQLError, httpx.HTTPError):
                    logger.debug("Failed to fetch collection %s rev %d", slug, rev_num)
                    continue

                mod_files = revision.get("modFiles") or []
                collection_mod_ids: dict[int, str] = {}
                for mf in mod_files:
                    file_data = mf.get("file") or {}
                    mod = file_data.get("mod") or {}
                    mid = mod.get("modId")
                    name = mod.get("name", "")
                    if mid:
                        collection_mod_ids[mid] = name

                # Check overlap
                overlap = correlated_nexus_ids & set(collection_mod_ids.keys())
                if len(overlap) < _MIN_COLLECTION_OVERLAP:
                    continue

                collections_checked += 1
                logger.info(
                    "Collection '%s' has %d/%d mods in common with correlated set",
                    coll.get("name", slug),
                    len(overlap),
                    len(collection_mod_ids),
                )

                # Find unmatched collection mods
                uncorrelated_collection = {
                    mid: name
                    for mid, name in collection_mod_ids.items()
                    if mid not in correlated_nexus_ids and mid not in newly_matched_nexus_ids
                }

                for group in unmatched_groups:
                    if group.id in newly_matched_groups:
                        continue

                    best_mid: int | None = None
                    best_score = 0.0
                    best_name = ""

                    for mid, name in uncorrelated_collection.items():
                        if mid in newly_matched_nexus_ids:
                            continue
                        score, _ = compute_name_score(group.display_name, name)
                        if score >= _NAME_THRESHOLD and score > best_score:
                            best_score = score
                            best_mid = mid
                            best_name = name

                    if best_mid is None:
                        continue

                    # Find or create NexusDownload
                    dl = session.exec(
                        select(NexusDownload).where(
                            NexusDownload.game_id == game.id,
                            NexusDownload.nexus_mod_id == best_mid,
                        )
                    ).first()

                    if not dl:
                        dl = upsert_nexus_mod(
                            session,
                            game.id,  # type: ignore[arg-type]
                            game.domain_name,
                            best_mid,
                            {"name": best_name},
                        )
                        session.flush()

                    # Guard: skip if group already has a correlation from a prior phase
                    existing_group_corr = session.exec(
                        select(ModNexusCorrelation).where(
                            ModNexusCorrelation.mod_group_id == group.id
                        )
                    ).first()
                    if existing_group_corr:
                        continue

                    # Guard: skip if nexus download already correlated to another group
                    existing_dl_corr = session.exec(
                        select(ModNexusCorrelation).where(
                            ModNexusCorrelation.nexus_download_id == dl.id
                        )
                    ).first()
                    if existing_dl_corr:
                        continue

                    corr = ModNexusCorrelation(
                        mod_group_id=group.id,  # type: ignore[arg-type]
                        nexus_download_id=dl.id,  # type: ignore[arg-type]
                        score=_CORRELATION_SCORE,
                        method="collection",
                        reasoning=(
                            f"Matched via collection '{coll.get('name', slug)}': "
                            f"'{group.display_name}' -> '{best_name}' "
                            f"(score {best_score:.2f})"
                        ),
                    )
                    session.add(corr)
                    newly_matched_groups.add(group.id)  # type: ignore[arg-type]
                    newly_matched_nexus_ids.add(best_mid)
                    matched += 1

                    logger.info(
                        "Collection match: '%s' -> mod %d ('%s') via '%s'",
                        group.display_name,
                        best_mid,
                        best_name,
                        coll.get("name", slug),
                    )

    except NexusRateLimitError:
        logger.warning("Rate limited during collection matching")
    except httpx.HTTPError:
        logger.warning("Collection matching failed", exc_info=True)

    if matched:
        session.commit()
        on_progress("collections", f"Collections: {matched} matched", 98)

    return RequirementMatchResult(requirements_checked=collections_checked, matched=matched)
