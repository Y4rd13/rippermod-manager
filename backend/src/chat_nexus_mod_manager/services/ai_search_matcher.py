"""AI-powered web search for unmatched mod groups.

Uses OpenAI's Responses API with the built-in ``web_search`` tool so the model
can reason about file names, extensions, and folder structures to find the
correct Nexus Mods page.
"""

import asyncio
import json
import logging
import re

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlmodel import Session, select

from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModFile, ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload
from chat_nexus_mod_manager.nexus.client import NexusClient, NexusRateLimitError
from chat_nexus_mod_manager.schemas.mod import WebSearchResult
from chat_nexus_mod_manager.services.nexus_helpers import upsert_nexus_mod
from chat_nexus_mod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)

_CONCURRENCY = 5
_MAX_SEARCHES = 30
_SEARCH_TIMEOUT = 180  # seconds
_MODEL = "gpt-5-mini"
_MAX_OUTPUT_TOKENS = 1024
_NEXUS_MOD_ID_RE = re.compile(r"nexusmods\.com/\w+/mods/(\d+)")
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)

_SYSTEM_PROMPT = """\
You are a mod identification specialist for PC games. Given information about
locally-installed mod files, search nexusmods.com to find the exact mod page.

Context clues:
- .archive/.xl files in archive/pc/mod/ → archive replacement mods
- .lua files in bin/x64/plugins/cyber_engine_tweaks/mods/ → CET script mods
- .reds files in r6/scripts/ → REDscript mods
- .dll files in bin/x64/plugins/ → RED4ext framework/plugins
- info.json in mods/ → REDmod packages

If a list of user's endorsed/tracked Nexus mods is provided, check those FIRST
— the user very likely installed one of them. Folder names are strong mod
identity signals (users rarely rename mod folders after installing).

Return JSON with: nexus_mod_id, confidence (0-1), reasoning, nexus_url.
Only match if confident. Do NOT guess.\
"""

_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "name": "ai_search_match",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "nexus_mod_id": {
                "type": ["integer", "null"],
                "description": "Nexus mod ID if found, null otherwise",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence 0-1",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of match or why not found",
            },
            "nexus_url": {
                "type": ["string", "null"],
                "description": "Full Nexus URL if found",
            },
        },
        "required": ["nexus_mod_id", "confidence", "reasoning", "nexus_url"],
        "additionalProperties": False,
    },
}


class AISearchMatch(BaseModel):
    nexus_mod_id: int | None = None
    confidence: float = 0.0
    reasoning: str = ""
    nexus_url: str | None = None


def _build_user_prompt(
    group: ModGroup,
    files: list[ModFile],
    game: Game,
    endorsed_hints: list[tuple[str, int]] | None = None,
) -> str:
    """Build a rich context prompt for one mod group."""
    file_lines: list[str] = []
    extensions: set[str] = set()
    folders: set[str] = set()
    total_size = 0
    for f in files[:20]:
        file_lines.append(f"  - {f.file_path} ({f.file_size:,} bytes)")
        ext = f.filename.rsplit(".", 1)[-1] if "." in f.filename else ""
        if ext:
            extensions.add(f".{ext}")
        if f.source_folder:
            folders.add(f.source_folder)
    for f in files:
        total_size += f.file_size

    size_mb = total_size / (1024 * 1024)

    parts = [
        f"Game: {game.name} (domain: {game.domain_name})",
        f"Mod group name: {group.display_name}",
        f"File count: {len(files)}, total size: {size_mb:.1f} MB",
        f"Extensions: {', '.join(sorted(extensions)) or 'unknown'}",
        f"Source folders: {', '.join(sorted(folders)) or 'unknown'}",
        f"Files (first {min(len(files), 20)}):",
        *file_lines,
    ]

    if endorsed_hints:
        parts.append("")
        parts.append("User's endorsed/tracked Nexus mods (potential matches):")
        for name, mod_id in endorsed_hints[:15]:
            parts.append(f"  - {name} (nexus_mod_id: {mod_id})")

    return "\n".join(parts)


async def ai_search_unmatched_mods(
    game: Game,
    openai_key: str,
    nexus_api_key: str,
    session: Session,
    on_progress: ProgressCallback = noop_progress,
    max_searches: int = _MAX_SEARCHES,
) -> WebSearchResult:
    """Search the web using AI for unmatched mod groups and create correlations."""
    all_groups = session.exec(select(ModGroup).where(ModGroup.game_id == game.id)).all()
    matched_group_ids = set(
        session.exec(
            select(ModNexusCorrelation.mod_group_id).where(
                ModNexusCorrelation.mod_group_id.in_([g.id for g in all_groups])  # type: ignore[union-attr]
            )
        ).all()
    )

    unmatched = [g for g in all_groups if g.id not in matched_group_ids]
    unmatched.sort(key=lambda g: g.confidence, reverse=True)
    unmatched = unmatched[:max_searches]

    if not unmatched:
        on_progress("ai-search", "All groups already matched", 100)
        return WebSearchResult(searched=0, matched=0, unmatched=0)

    # Build endorsed mod hints for the AI prompt
    endorsed_dls = session.exec(
        select(NexusDownload).where(
            NexusDownload.game_id == game.id,
            (NexusDownload.is_endorsed.is_(True)) | (NexusDownload.is_tracked.is_(True)),
        )
    ).all()
    endorsed_corr_dl_ids = set(session.exec(select(ModNexusCorrelation.nexus_download_id)).all())
    endorsed_hints: list[tuple[str, int]] = [
        (dl.mod_name, dl.nexus_mod_id) for dl in endorsed_dls if dl.id not in endorsed_corr_dl_ids
    ]

    on_progress("ai-search", f"AI searching {len(unmatched)} unmatched groups...", 99)

    client = AsyncOpenAI(api_key=openai_key)
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    found: dict[int, AISearchMatch] = {}  # group_id -> match

    async def search_one(group: ModGroup) -> None:
        async with semaphore:
            files = session.exec(select(ModFile).where(ModFile.mod_group_id == group.id)).all()
            user_prompt = _build_user_prompt(group, files, game, endorsed_hints)

            try:
                response = await client.responses.create(
                    model=_MODEL,
                    instructions=_SYSTEM_PROMPT,
                    input=user_prompt,
                    tools=[{"type": "web_search"}],
                    text={"format": _RESPONSE_SCHEMA},
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                )

                raw = response.output_text
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    # Model may wrap JSON in markdown or return truncated output;
                    # attempt to extract the first complete JSON object.
                    m = _JSON_OBJECT_RE.search(raw)
                    if not m:
                        logger.warning(
                            "AI search: no valid JSON in response for '%s': %s",
                            group.display_name,
                            raw[:200],
                        )
                        return
                    data = json.loads(m.group())
                match = AISearchMatch(**data)

                if match.nexus_mod_id and match.confidence > 0:
                    match.confidence = min(match.confidence, 0.90)

                    # Validate mod ID from URL if provided
                    if match.nexus_url:
                        m = _NEXUS_MOD_ID_RE.search(match.nexus_url)
                        if m:
                            match.nexus_mod_id = int(m.group(1))

                    found[group.id] = match  # type: ignore[arg-type]

            except Exception:
                logger.warning("AI search failed for '%s'", group.display_name, exc_info=True)

    tasks = [search_one(g) for g in unmatched]
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=_SEARCH_TIMEOUT)
    except TimeoutError:
        logger.warning("AI search timed out after %ds", _SEARCH_TIMEOUT)

    searched = len(unmatched)
    on_progress("ai-search", f"Found {len(found)} matches, fetching mod info...", 99)

    matched_count = 0

    # Track nexus_mod_ids already correlated to prevent duplicates
    corr_nexus_ids: set[int] = set()
    for corr_row in session.exec(
        select(ModNexusCorrelation, NexusDownload).join(
            NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id
        )
    ).all():
        corr_nexus_ids.add(corr_row[1].nexus_mod_id)

    async with NexusClient(nexus_api_key) as nexus:
        for group_id, match in found.items():
            mod_id = match.nexus_mod_id
            if mod_id is None:
                continue

            if mod_id in corr_nexus_ids:
                logger.info("AI search: skipping mod %d, already correlated", mod_id)
                continue

            existing_dl = session.exec(
                select(NexusDownload).where(
                    NexusDownload.game_id == game.id,
                    NexusDownload.nexus_mod_id == mod_id,
                )
            ).first()

            if not existing_dl:
                if nexus.hourly_remaining is not None and nexus.hourly_remaining < 5:
                    logger.warning("Rate limit low, stopping AI search enrichment")
                    break

                try:
                    info = await nexus.get_mod_info(game.domain_name, mod_id)
                except NexusRateLimitError:
                    logger.warning("Rate limited during AI search enrichment")
                    break
                except Exception:
                    logger.warning("Failed to fetch mod info for %s/%d", game.domain_name, mod_id)
                    continue

                dl = upsert_nexus_mod(
                    session,
                    game.id,  # type: ignore[arg-type]
                    game.domain_name,
                    mod_id,
                    info,
                )
                session.flush()
                existing_dl = dl

            group = next((g for g in unmatched if g.id == group_id), None)
            group_name = group.display_name if group else "unknown"

            corr = ModNexusCorrelation(
                mod_group_id=group_id,
                nexus_download_id=existing_dl.id,  # type: ignore[arg-type]
                score=match.confidence,
                method="ai_search",
                reasoning=match.reasoning or f"AI search matched '{group_name}'",
            )
            session.add(corr)
            corr_nexus_ids.add(mod_id)
            matched_count += 1

    session.commit()
    unmatched_count = searched - matched_count
    logger.info(
        "AI search: searched=%d, matched=%d, unmatched=%d",
        searched,
        matched_count,
        unmatched_count,
    )
    return WebSearchResult(
        searched=searched,
        matched=matched_count,
        unmatched=unmatched_count,
    )
