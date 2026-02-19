import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import engine
from chat_nexus_mod_manager.models.chat import ChatMessage
from chat_nexus_mod_manager.schemas.chat import ReasoningEffort
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.models.settings import AppSetting

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Role: You are a mod manager assistant for PC games, specializing in Cyberpunk 2077.

Capabilities:
- Search local mod database (search_local_mods, get_mod_details)
- Semantic search across all mod data (semantic_mod_search) — prefer for broad/fuzzy queries
- Query Nexus Mods metadata (get_nexus_mod_info, list_nexus_downloads)
- List configured games (list_all_games)
- Rebuild search index (reindex_vector_store)

Instructions:
1. For broad questions, use semantic_mod_search first, then refine with exact lookups.
2. Reference specific mod names, versions, and authors when available.
3. For conflict or load order questions, provide actionable advice.
4. Be concise. Avoid repeating the user's question back to them.
"""


def _get_openai_key() -> str:
    with Session(engine) as session:
        setting = session.exec(select(AppSetting).where(AppSetting.key == "openai_api_key")).first()
        return setting.value if setting else ""


def _get_model_name() -> str:
    with Session(engine) as session:
        setting = session.exec(select(AppSetting).where(AppSetting.key == "openai_model")).first()
        return setting.value if setting else "gpt-4o"


@tool
def search_local_mods(query: str, game_name: str = "") -> str:
    """Search for mods in the local database by name.

    Returns matching mod groups with their files and nexus match info.
    """
    with Session(engine) as session:
        stmt = select(ModGroup)
        if game_name:
            game = session.exec(select(Game).where(Game.name == game_name)).first()
            if game:
                stmt = stmt.where(ModGroup.game_id == game.id)

        groups = session.exec(stmt).all()
        matches = [g for g in groups if query.lower() in g.display_name.lower()]

        if not matches:
            return f"No mods found matching '{query}'"

        results = []
        for g in matches[:10]:
            _ = g.files
            files_str = ", ".join(f.filename for f in g.files[:5])
            results.append(f"- {g.display_name} ({len(g.files)} files: {files_str})")
        return "\n".join(results)


@tool
def get_mod_details(mod_name: str) -> str:
    """Get detailed information about a specific mod group including all files and nexus match."""
    with Session(engine) as session:
        group = session.exec(
            select(ModGroup).where(
                ModGroup.display_name.contains(mod_name)  # type: ignore[arg-type]
            )
        ).first()
        if not group:
            return f"Mod '{mod_name}' not found"

        _ = group.files
        info = [f"Mod: {group.display_name}", f"Confidence: {group.confidence}"]
        info.append("Files:")
        for f in group.files:
            info.append(f"  - {f.file_path} ({f.file_size} bytes)")
        return "\n".join(info)


@tool
def list_all_games() -> str:
    """List all configured games with their mod counts."""
    with Session(engine) as session:
        games = session.exec(select(Game)).all()
        if not games:
            return "No games configured"
        results = []
        for g in games:
            mod_count = len(session.exec(select(ModGroup).where(ModGroup.game_id == g.id)).all())
            results.append(f"- {g.name} ({mod_count} mod groups, path: {g.install_path})")
        return "\n".join(results)


@tool
def get_nexus_mod_info(nexus_mod_id: int) -> str:
    """Get cached Nexus metadata for a specific mod by its Nexus ID."""
    with Session(engine) as session:
        meta = session.exec(
            select(NexusModMeta).where(NexusModMeta.nexus_mod_id == nexus_mod_id)
        ).first()
        if not meta:
            return f"No cached info for Nexus mod #{nexus_mod_id}"
        return (
            f"Name: {meta.name}\n"
            f"Author: {meta.author}\n"
            f"Version: {meta.version}\n"
            f"Summary: {meta.summary}\n"
            f"Endorsements: {meta.endorsement_count}"
        )


@tool
def list_nexus_downloads(game_name: str = "") -> str:
    """List all synced Nexus downloads for a game."""
    with Session(engine) as session:
        stmt = select(NexusDownload)
        if game_name:
            game = session.exec(select(Game).where(Game.name == game_name)).first()
            if game:
                stmt = stmt.where(NexusDownload.game_id == game.id)

        downloads = session.exec(stmt).all()
        if not downloads:
            return "No Nexus downloads synced"

        results = []
        for d in downloads[:20]:
            results.append(f"- {d.mod_name} v{d.version} (Nexus #{d.nexus_mod_id})")
        if len(downloads) > 20:
            results.append(f"... and {len(downloads) - 20} more")
        return "\n".join(results)


@tool
def semantic_mod_search(query: str) -> str:
    """Search across all mod data using semantic/natural language search.

    Use this when the user asks broad questions about mods,
    troubleshooting, compatibility, or when exact name matching
    isn't enough. Returns the most relevant mod information from
    local mods, Nexus metadata, and correlation data.
    """
    from chat_nexus_mod_manager.vector.search import search_all_semantic

    return search_all_semantic(query, n_results=6)


@tool
def reindex_vector_store(game_name: str = "") -> str:
    """Rebuild the semantic search index from current database data.

    Run this after scanning mods or syncing Nexus data to update
    the search index.
    """
    from chat_nexus_mod_manager.vector.indexer import index_all

    game_id = None
    if game_name:
        with Session(engine) as session:
            game = session.exec(select(Game).where(Game.name == game_name)).first()
            if game:
                game_id = game.id

    counts = index_all(game_id)
    return (
        f"Reindexed: {counts['mod_groups']} mod groups, "
        f"{counts['nexus_mods']} Nexus mods, "
        f"{counts['correlations']} correlations"
    )


TOOLS = [
    search_local_mods,
    get_mod_details,
    list_all_games,
    get_nexus_mod_info,
    list_nexus_downloads,
    semantic_mod_search,
    reindex_vector_store,
]


async def run_agent(
    message: str,
    game_name: str | None = None,
    reasoning_effort: ReasoningEffort = "none",
) -> AsyncGenerator[dict[str, Any], None]:
    api_key = _get_openai_key()
    if not api_key:
        yield {
            "type": "token",
            "data": {"content": "OpenAI API key not configured. Please set it in Settings."},
        }
        return

    model_name = _get_model_name()
    use_reasoning = reasoning_effort != "none"

    llm_kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": api_key,
        "streaming": True,
    }
    if use_reasoning:
        llm_kwargs["temperature"] = 1
        llm_kwargs["model_kwargs"] = {"reasoning": {"effort": reasoning_effort}}
    else:
        llm_kwargs["temperature"] = 0.3

    llm = ChatOpenAI(**llm_kwargs)
    llm_with_tools = llm.bind_tools(TOOLS)

    with Session(engine) as session:
        history_rows = session.exec(
            select(ChatMessage)
            .order_by(ChatMessage.created_at.desc())  # type: ignore[arg-type]
            .limit(20)
        ).all()

    messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT)]
    for row in reversed(history_rows):
        if row.role == "user":
            messages.append(HumanMessage(content=row.content))
        elif row.role == "assistant":
            messages.append(AIMessage(content=row.content))

    if not any(isinstance(m, HumanMessage) and m.content == message for m in messages):
        messages.append(HumanMessage(content=message))

    if game_name:
        messages[-1] = HumanMessage(
            content=f"[Context: Currently viewing game '{game_name}']\n\n{message}"
        )

    max_iterations = 5
    for _ in range(max_iterations):
        full_content = ""
        emitted_thinking_start = False
        emitted_thinking_end = False

        if use_reasoning:
            yield {"type": "thinking_start", "data": {"effort": reasoning_effort}}
            emitted_thinking_start = True

        # Concatenate AIMessageChunks to properly merge streamed tool calls
        gathered = None
        async for chunk in llm_with_tools.astream(messages):
            if chunk.content:
                text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                if emitted_thinking_start and not emitted_thinking_end:
                    yield {"type": "thinking_end", "data": {}}
                    emitted_thinking_end = True
                full_content += text
                yield {"type": "token", "data": {"content": text}}
            gathered = chunk if gathered is None else gathered + chunk

        # If thinking started but no content tokens arrived (tool-call-only), still end it
        if emitted_thinking_start and not emitted_thinking_end:
            yield {"type": "thinking_end", "data": {}}

        tool_calls_data: list[dict[str, Any]] = []
        if gathered and hasattr(gathered, "tool_calls"):
            tool_calls_data = list(gathered.tool_calls)

        if not tool_calls_data:
            with Session(engine) as session:
                session.add(ChatMessage(role="assistant", content=full_content))
                session.commit()
            break

        # Ensure every tool call has a valid string id
        for i, tc in enumerate(tool_calls_data):
            if not tc.get("id"):
                tc["id"] = f"call_{tc['name']}_{i}"

        ai_msg = AIMessage(content=full_content, tool_calls=tool_calls_data)
        messages.append(ai_msg)

        from langchain_core.messages import ToolMessage

        for tc in tool_calls_data:
            yield {
                "type": "tool_call",
                "data": {"name": tc["name"], "args": tc["args"]},
            }

            tool_fn = {t.name: t for t in TOOLS}.get(tc["name"])
            if tool_fn:
                try:
                    result = tool_fn.invoke(tc["args"])
                except Exception as e:
                    result = f"Error: {e}"
            else:
                result = f"Unknown tool: {tc['name']}"

            yield {
                "type": "tool_result",
                "data": {"name": tc["name"], "result": str(result)[:500]},
            }

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        with Session(engine) as session:
            session.add(
                ChatMessage(
                    role="assistant",
                    content=full_content,
                    tool_calls_json=json.dumps(
                        [{"name": tc["name"], "args": tc["args"]} for tc in tool_calls_data]
                    ),
                )
            )
            session.commit()

    suggestions = _generate_suggestions(message, game_name)
    if suggestions:
        yield {"type": "suggested_actions", "data": {"actions": suggestions}}


def _generate_suggestions(message: str, game_name: str | None) -> list[str]:
    suggestions = []
    lower = message.lower()
    if "scan" in lower or "mods" in lower:
        suggestions.append("Show me all installed mods")
    if "update" in lower:
        suggestions.append("Check for updates")
    if game_name:
        suggestions.append(f"List all mods for {game_name}")
    if not suggestions:
        suggestions = [
            "What mods do I have installed?",
            "Check for mod updates",
            "Help me troubleshoot mod conflicts",
        ]
    return suggestions[:3]
