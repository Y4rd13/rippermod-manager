import asyncio
import json
import logging
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from rippermod_manager.database import engine, get_session
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.game import Game
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModMeta
from rippermod_manager.schemas.mod import (
    CorrelateResult,
    CorrelationBrief,
    CorrelationReassign,
    ModGroupOut,
    ScanResult,
    ScanStreamRequest,
)
from rippermod_manager.services.update_service import batch_group_file_mtimes

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

    # Deduplicate across groups: if multiple groups match the same nexus_mod_id,
    # only the group with the highest score keeps the match.
    nexus_id_best: dict[int, tuple[int, float]] = {}  # nexus_mod_id -> (group_id, score)
    for group_id, (corr, nd, _meta) in corr_map.items():
        nid = nd.nexus_mod_id
        prev = nexus_id_best.get(nid)
        if prev is None or corr.score > prev[1]:
            nexus_id_best[nid] = (group_id, corr.score)

    nexus_id_winner: set[int] = set()  # group_ids that won dedup
    for _nid, (group_id, _score) in nexus_id_best.items():
        nexus_id_winner.add(group_id)

    mtime_map = batch_group_file_mtimes(group_ids, game.install_path, session)

    result: list[ModGroupOut] = []
    for g in groups:
        _ = g.files
        nexus_match = None
        match = corr_map.get(g.id)  # type: ignore[arg-type]
        if match and g.id in nexus_id_winner:
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
                updated_at=meta.updated_at if meta else None,
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
                earliest_file_mtime=mtime_map.get(g.id),  # type: ignore[arg-type]
            )
        )
    return result


@router.post("/scan", response_model=ScanResult)
def scan_mods(game_name: str, session: Session = Depends(get_session)) -> ScanResult:
    game = _get_game(game_name, session)
    _ = game.mod_paths

    from rippermod_manager.scanner.service import scan_game_mods

    return scan_game_mods(game, session)


@router.post("/scan-stream")
def scan_mods_stream(game_name: str, body: ScanStreamRequest | None = None) -> StreamingResponse:
    use_ai_search = body.ai_search if body else False
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

                from rippermod_manager.matching.correlator import correlate_game_mods
                from rippermod_manager.scanner.service import scan_game_mods
                from rippermod_manager.services.archive_matcher import match_archives_by_md5
                from rippermod_manager.services.enrichment import enrich_from_filename_ids
                from rippermod_manager.services.file_list_matcher import (
                    match_endorsed_by_name,
                    match_endorsed_to_local,
                )
                from rippermod_manager.services.fomod_parser import parse_archive_metadata
                from rippermod_manager.services.nexus_sync import sync_nexus_history
                from rippermod_manager.services.settings_helpers import get_setting
                from rippermod_manager.services.web_search_matcher import (
                    search_unmatched_mods,
                )

                openai_key = get_setting(session, "openai_api_key") if use_ai_search else None

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

                        # File list matching (97%) — between sync and correlate
                        on_progress("file-list", "Matching endorsed mods to local files...", 97)
                        fl_result = match_endorsed_to_local(game, session, on_progress)
                        if fl_result.matched:
                            on_progress(
                                "file-list",
                                f"File list: {fl_result.matched} endorsed mods matched",
                                97,
                            )

                        # Endorsed name matching (97%) — catch mods without archives
                        on_progress("endorsed-name", "Matching endorsed mods by name...", 97)
                        en_result = match_endorsed_by_name(game, session)
                        if en_result.matched:
                            on_progress(
                                "endorsed-name",
                                f"Endorsed name: {en_result.matched} mods matched",
                                97,
                            )

                    # Correlate (97-99%)
                    on_progress("correlate", "Correlating mods...", 97)
                    result = correlate_game_mods(game, session)
                    on_progress(
                        "correlate",
                        f"Correlated: {result.matched} matched, {result.unmatched} unmatched",
                        99,
                    )

                    if use_ai_search and openai_key and api_key:
                        from rippermod_manager.services.ai_search_matcher import (
                            ai_search_unmatched_mods,
                        )

                        on_progress("ai-search", "AI searching unmatched mods...", 99)
                        await ai_search_unmatched_mods(
                            game, openai_key, api_key, session, on_progress
                        )
                    elif api_key and tavily_key:
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


@router.patch("/{mod_group_id}/correlation/confirm", response_model=CorrelationBrief)
def confirm_correlation(
    game_name: str, mod_group_id: int, session: Session = Depends(get_session)
) -> CorrelationBrief:
    _get_game(game_name, session)
    corr = session.exec(
        select(ModNexusCorrelation)
        .where(ModNexusCorrelation.mod_group_id == mod_group_id)
        .order_by(ModNexusCorrelation.score.desc())  # type: ignore[union-attr]
    ).first()
    if not corr:
        raise HTTPException(404, "No correlation found for this mod group")
    corr.confirmed_by_user = True
    session.add(corr)
    session.commit()
    session.refresh(corr)
    dl = session.get(NexusDownload, corr.nexus_download_id)
    if not dl:
        raise HTTPException(404, "NexusDownload not found")
    meta = session.exec(
        select(NexusModMeta).where(NexusModMeta.nexus_mod_id == dl.nexus_mod_id)
    ).first()
    return CorrelationBrief(
        nexus_mod_id=dl.nexus_mod_id,
        mod_name=dl.mod_name,
        score=corr.score,
        method=corr.method,
        confirmed=corr.confirmed_by_user,
        author=meta.author if meta else "",
        summary=meta.summary if meta else "",
        version=meta.version if meta else dl.version,
        endorsement_count=meta.endorsement_count if meta else 0,
        category=meta.category if meta else "",
        picture_url=meta.picture_url if meta else "",
        nexus_url=dl.nexus_url,
        updated_at=meta.updated_at if meta else None,
    )


@router.delete("/{mod_group_id}/correlation")
def reject_correlation(
    game_name: str, mod_group_id: int, session: Session = Depends(get_session)
) -> dict[str, bool]:
    _get_game(game_name, session)
    corrs = session.exec(
        select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == mod_group_id)
    ).all()
    if not corrs:
        raise HTTPException(404, "No correlations found for this mod group")
    for c in corrs:
        session.delete(c)
    session.commit()
    return {"deleted": True}


@router.put("/{mod_group_id}/correlation", response_model=CorrelationBrief)
async def reassign_correlation(
    game_name: str,
    mod_group_id: int,
    body: CorrelationReassign,
    session: Session = Depends(get_session),
) -> CorrelationBrief:
    game = _get_game(game_name, session)

    # Delete existing correlations
    existing = session.exec(
        select(ModNexusCorrelation).where(ModNexusCorrelation.mod_group_id == mod_group_id)
    ).all()
    for c in existing:
        session.delete(c)
    session.flush()

    # Find or create NexusDownload
    dl = session.exec(
        select(NexusDownload).where(
            NexusDownload.game_id == game.id,
            NexusDownload.nexus_mod_id == body.nexus_mod_id,
        )
    ).first()

    if not dl:
        from rippermod_manager.nexus.client import NexusClient
        from rippermod_manager.services.nexus_helpers import upsert_nexus_mod
        from rippermod_manager.services.settings_helpers import get_setting

        api_key = get_setting(session, "nexus_api_key")
        if not api_key:
            raise HTTPException(400, "Nexus API key not configured")

        async with NexusClient(api_key) as client:
            info = await client.get_mod_info(game.domain_name, body.nexus_mod_id)

        dl = upsert_nexus_mod(
            session,
            game.id,
            game.domain_name,
            body.nexus_mod_id,
            info,  # type: ignore[arg-type]
        )
        session.flush()

    corr = ModNexusCorrelation(
        mod_group_id=mod_group_id,
        nexus_download_id=dl.id,  # type: ignore[arg-type]
        score=1.0,
        method="manual",
        reasoning=f"Manually assigned to nexus_mod_id={body.nexus_mod_id}",
        confirmed_by_user=True,
    )
    session.add(corr)
    session.commit()

    meta = session.exec(
        select(NexusModMeta).where(NexusModMeta.nexus_mod_id == dl.nexus_mod_id)
    ).first()
    return CorrelationBrief(
        nexus_mod_id=dl.nexus_mod_id,
        mod_name=dl.mod_name,
        score=corr.score,
        method=corr.method,
        confirmed=corr.confirmed_by_user,
        author=meta.author if meta else "",
        summary=meta.summary if meta else "",
        version=meta.version if meta else dl.version,
        endorsement_count=meta.endorsement_count if meta else 0,
        category=meta.category if meta else "",
        picture_url=meta.picture_url if meta else "",
        nexus_url=dl.nexus_url,
        updated_at=meta.updated_at if meta else None,
    )


@router.post("/correlate", response_model=CorrelateResult)
def correlate_mods(game_name: str, session: Session = Depends(get_session)) -> CorrelateResult:
    game = _get_game(game_name, session)

    from rippermod_manager.matching.correlator import correlate_game_mods

    return correlate_game_mods(game, session)
