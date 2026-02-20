import asyncio
import json
import logging
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import engine, get_session
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta
from chat_nexus_mod_manager.schemas.mod import (
    CorrelateResult,
    CorrelationBrief,
    ModGroupOut,
    ScanResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/mods", tags=["mods"])


def _get_game(game_name: str, session: Session) -> Game:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")
    return game


@router.get("/", response_model=list[ModGroupOut])
def list_mod_groups(game_name: str, session: Session = Depends(get_session)) -> list[ModGroupOut]:
    game = _get_game(game_name, session)
    groups = session.exec(select(ModGroup).where(ModGroup.game_id == game.id)).all()

    group_ids = [g.id for g in groups]
    corr_rows = session.exec(
        select(ModNexusCorrelation, NexusDownload, NexusModMeta)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .outerjoin(NexusModMeta, NexusDownload.nexus_mod_id == NexusModMeta.nexus_mod_id)
        .where(ModNexusCorrelation.mod_group_id.in_(group_ids))  # type: ignore[union-attr]
    ).all()
    corr_map: dict[int, tuple[ModNexusCorrelation, NexusDownload, NexusModMeta | None]] = {}
    for corr, nd, meta in corr_rows:
        existing = corr_map.get(corr.mod_group_id)
        if existing is None or corr.score > existing[0].score:
            corr_map[corr.mod_group_id] = (corr, nd, meta)

    result: list[ModGroupOut] = []
    for g in groups:
        _ = g.files
        nexus_match = None
        match = corr_map.get(g.id)  # type: ignore[arg-type]
        if match:
            corr, nd, meta = match
            nexus_match = CorrelationBrief(
                nexus_mod_id=nd.nexus_mod_id,
                mod_name=nd.mod_name,
                score=corr.score,
                method=corr.method,
                confirmed=corr.confirmed_by_user,
                author=meta.author if meta else "",
                summary=meta.summary if meta else "",
                version=meta.version if meta else nd.version,
                endorsement_count=meta.endorsement_count if meta else 0,
                category=meta.category if meta else "",
                picture_url=meta.picture_url if meta else "",
                nexus_url=nd.nexus_url,
            )

        result.append(
            ModGroupOut(
                id=g.id,  # type: ignore[arg-type]
                game_id=g.game_id,
                display_name=g.display_name,
                confidence=g.confidence,
                files=[
                    {
                        "id": f.id,
                        "file_path": f.file_path,
                        "filename": f.filename,
                        "file_hash": f.file_hash,
                        "file_size": f.file_size,
                        "source_folder": f.source_folder,
                    }
                    for f in g.files
                ],
                nexus_match=nexus_match,
            )
        )
    return result


@router.post("/scan", response_model=ScanResult)
def scan_mods(game_name: str, session: Session = Depends(get_session)) -> ScanResult:
    game = _get_game(game_name, session)
    _ = game.mod_paths

    from chat_nexus_mod_manager.scanner.service import scan_game_mods

    return scan_game_mods(game, session)


@router.post("/scan-stream")
def scan_mods_stream(game_name: str) -> StreamingResponse:
    q: queue.Queue[dict | None] = queue.Queue()

    def on_progress(phase: str, message: str, percent: int) -> None:
        q.put({"phase": phase, "message": message, "percent": percent})

    def run_scan() -> None:
        try:
            with Session(engine) as session:
                game = session.exec(select(Game).where(Game.name == game_name)).first()
                if not game:
                    q.put(
                        {"phase": "error", "message": f"Game '{game_name}' not found", "percent": 0}
                    )
                    return
                _ = game.mod_paths

                from chat_nexus_mod_manager.matching.correlator import correlate_game_mods
                from chat_nexus_mod_manager.scanner.service import scan_game_mods
                from chat_nexus_mod_manager.services.archive_matcher import match_archives_by_md5
                from chat_nexus_mod_manager.services.enrichment import enrich_from_filename_ids
                from chat_nexus_mod_manager.services.fomod_parser import parse_archive_metadata
                from chat_nexus_mod_manager.services.nexus_sync import sync_nexus_history
                from chat_nexus_mod_manager.services.settings_helpers import get_setting
                from chat_nexus_mod_manager.services.web_search_matcher import (
                    search_unmatched_mods,
                )

                # Phase 1: Scan files + group (0-83%)
                scan_game_mods(game, session, on_progress=on_progress)

                # Phase 1.5: FOMOD/REDmod metadata (83-85%)
                on_progress("fomod", "Inspecting archive metadata...", 83)
                fomod_result = parse_archive_metadata(game, session, on_progress)
                session.commit()
                on_progress(
                    "fomod",
                    f"Found {fomod_result.fomod_found} FOMOD + {fomod_result.redmod_found} REDmod",
                    85,
                )

                api_key = get_setting(session, "nexus_api_key")
                tavily_key = get_setting(session, "tavily_api_key")

                async def _run_async_pipeline() -> None:
                    if api_key:
                        # Tier 1 — Filename ID enrichment (85-92%)
                        on_progress("enrich", "Enriching from filename IDs...", 85)
                        await enrich_from_filename_ids(game, api_key, session, on_progress)

                        # Tier 2 — MD5 archive matching (92-96%)
                        on_progress("md5", "Matching archives by MD5...", 92)
                        await match_archives_by_md5(game, api_key, session, on_progress)

                        # Nexus sync (96-97%)
                        on_progress("sync", "Syncing Nexus history...", 96)
                        await sync_nexus_history(game, api_key, session)
                        on_progress("sync", "Nexus sync complete", 97)

                    # Correlate (97-99%)
                    on_progress("correlate", "Correlating mods...", 97)
                    result = correlate_game_mods(game, session)
                    on_progress(
                        "correlate",
                        f"Correlated: {result.matched} matched, {result.unmatched} unmatched",
                        99,
                    )

                    if api_key and tavily_key:
                        # Tier 3 — Web search fallback (99-100%)
                        try:
                            on_progress("web-search", "Searching unmatched mods...", 99)
                            await search_unmatched_mods(
                                game, api_key, tavily_key, session, on_progress
                            )
                        except ImportError:
                            on_progress(
                                "web-search",
                                "Skipped (install tavily-python for web search)",
                                99,
                            )

                    on_progress("done", f"Done: {result.matched} matched", 100)

                asyncio.run(_run_async_pipeline())
        except Exception:
            logger.exception("Scan failed for game '%s'", game_name)
            q.put({"phase": "error", "message": "Scan failed unexpectedly", "percent": 0})
        finally:
            q.put(None)

    threading.Thread(target=run_scan, daemon=True).start()

    def event_stream():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/correlate", response_model=CorrelateResult)
def correlate_mods(game_name: str, session: Session = Depends(get_session)) -> CorrelateResult:
    game = _get_game(game_name, session)

    from chat_nexus_mod_manager.matching.correlator import correlate_game_mods

    return correlate_game_mods(game, session)
