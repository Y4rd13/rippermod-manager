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
from chat_nexus_mod_manager.models.nexus import NexusDownload
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
        select(ModNexusCorrelation, NexusDownload)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .where(ModNexusCorrelation.mod_group_id.in_(group_ids))  # type: ignore[union-attr]
    ).all()
    corr_map: dict[int, tuple[ModNexusCorrelation, NexusDownload]] = {}
    for corr, nd in corr_rows:
        existing = corr_map.get(corr.mod_group_id)
        if existing is None or corr.score > existing[0].score:
            corr_map[corr.mod_group_id] = (corr, nd)

    result: list[ModGroupOut] = []
    for g in groups:
        _ = g.files
        nexus_match = None
        match = corr_map.get(g.id)  # type: ignore[arg-type]
        if match:
            corr, nd = match
            nexus_match = CorrelationBrief(
                nexus_mod_id=nd.nexus_mod_id,
                mod_name=nd.mod_name,
                score=corr.score,
                method=corr.method,
                confirmed=corr.confirmed_by_user,
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

                from chat_nexus_mod_manager.scanner.service import scan_game_mods

                scan_game_mods(game, session, on_progress=on_progress)
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
