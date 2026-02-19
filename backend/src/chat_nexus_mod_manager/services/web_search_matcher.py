"""Tier 3: Tavily web search fallback for unmatched mod groups.

Searches the web for unmatched mod groups, parses Nexus URLs from results,
and creates correlations for confident matches.
"""

import asyncio
import logging
import re
from collections.abc import Callable

from sqlmodel import Session, select

from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.nexus.client import NexusClient, NexusRateLimitError
from chat_nexus_mod_manager.schemas.mod import WebSearchResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]

_NEXUS_MOD_ID_RE = re.compile(r"nexusmods\.com/\w+/mods/(\d+)")
_CONCURRENCY = 10


def _noop(_phase: str, _msg: str, _pct: int) -> None:
    pass


async def search_unmatched_mods(
    game: Game,
    api_key: str,
    tavily_key: str,
    session: Session,
    on_progress: ProgressCallback = _noop,
    max_searches: int = 50,
) -> WebSearchResult:
    """Search the web for unmatched mod groups and create correlations."""
    from tavily import AsyncTavilyClient

    # Find groups without a correlation
    all_groups = session.exec(select(ModGroup).where(ModGroup.game_id == game.id)).all()
    matched_group_ids = set(
        session.exec(
            select(ModNexusCorrelation.mod_group_id).where(
                ModNexusCorrelation.mod_group_id.in_([g.id for g in all_groups])  # type: ignore[union-attr]
            )
        ).all()
    )

    unmatched = [g for g in all_groups if g.id not in matched_group_ids]
    # Sort by confidence desc — prioritize well-grouped mods
    unmatched.sort(key=lambda g: g.confidence, reverse=True)
    unmatched = unmatched[:max_searches]

    if not unmatched:
        on_progress("web-search", "All groups already matched", 100)
        return WebSearchResult(searched=0, matched=0, unmatched=0)

    on_progress("web-search", f"Searching {len(unmatched)} unmatched groups...", 99)

    tavily = AsyncTavilyClient(api_key=tavily_key)
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    searched = 0
    matched_count = 0
    found_mod_ids: dict[int, dict] = {}  # group_id -> {nexus_mod_id, score, group_name}

    async def search_one(group: ModGroup) -> None:
        nonlocal searched
        async with semaphore:
            query = f"{group.display_name} {game.domain_name} site:nexusmods.com"
            try:
                result = await tavily.search(
                    query=query,
                    include_domains=["nexusmods.com"],
                    max_results=3,
                )
            except Exception:
                logger.warning("Tavily search failed for '%s'", group.display_name)
                return
            finally:
                searched += 1

            for r in result.get("results", []):
                url = r.get("url", "")
                score = r.get("score", 0)
                m = _NEXUS_MOD_ID_RE.search(url)
                if m and score > 0.5:
                    nexus_mod_id = int(m.group(1))
                    found_mod_ids[group.id] = {  # type: ignore[arg-type]
                        "nexus_mod_id": nexus_mod_id,
                        "score": min(score, 0.85),  # cap web search confidence
                        "group_name": group.display_name,
                    }
                    break

    tasks = [search_one(g) for g in unmatched]
    await asyncio.gather(*tasks)

    on_progress("web-search", f"Found {len(found_mod_ids)} matches, fetching mod info...", 99)

    # Fetch mod info and create correlations
    async with NexusClient(api_key) as client:
        for group_id, match_info in found_mod_ids.items():
            mod_id = match_info["nexus_mod_id"]

            # Check if NexusDownload already exists
            existing_dl = session.exec(
                select(NexusDownload).where(
                    NexusDownload.game_id == game.id,
                    NexusDownload.nexus_mod_id == mod_id,
                )
            ).first()

            if not existing_dl:
                # Rate limit check
                if client.hourly_remaining is not None and client.hourly_remaining < 5:
                    logger.warning("Rate limit low, stopping web search enrichment")
                    break

                try:
                    info = await client.get_mod_info(game.domain_name, mod_id)
                except NexusRateLimitError:
                    logger.warning("Rate limited during web search enrichment")
                    break
                except Exception:
                    logger.warning("Failed to fetch mod info for %s/%d", game.domain_name, mod_id)
                    continue

                nexus_url = f"https://www.nexusmods.com/{game.domain_name}/mods/{mod_id}"
                dl = NexusDownload(
                    game_id=game.id,  # type: ignore[arg-type]
                    nexus_mod_id=mod_id,
                    mod_name=info.get("name", ""),
                    version=info.get("version", ""),
                    category=str(info.get("category_id", "")),
                    nexus_url=nexus_url,
                )
                session.add(dl)
                session.flush()

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

                existing_dl = dl

            # Create correlation
            corr = ModNexusCorrelation(
                mod_group_id=group_id,
                nexus_download_id=existing_dl.id,  # type: ignore[arg-type]
                score=match_info["score"],
                method="web_search",
                reasoning=(
                    f"Web search matched '{match_info['group_name']}' "
                    f"-> '{existing_dl.mod_name}' via Tavily"
                ),
            )
            session.add(corr)
            matched_count += 1

    session.commit()
    unmatched_count = len(unmatched) - matched_count
    logger.info(
        "Web search: searched=%d, matched=%d, unmatched=%d",
        searched,
        matched_count,
        unmatched_count,
    )
    return WebSearchResult(
        searched=searched,
        matched=matched_count,
        unmatched=unmatched_count,
    )
