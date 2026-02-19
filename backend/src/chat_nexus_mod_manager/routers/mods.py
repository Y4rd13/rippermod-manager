from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
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

router = APIRouter(prefix="/games/{game_name}/mods", tags=["mods"])


def _get_game(game_name: str, session: Session) -> Game:
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")
    return game


@router.get("/", response_model=list[ModGroupOut])
def list_mod_groups(
    game_name: str, session: Session = Depends(get_session)
) -> list[ModGroupOut]:
    game = _get_game(game_name, session)
    groups = session.exec(
        select(ModGroup).where(ModGroup.game_id == game.id)
    ).all()

    result: list[ModGroupOut] = []
    for g in groups:
        _ = g.files
        corr = session.exec(
            select(ModNexusCorrelation).where(
                ModNexusCorrelation.mod_group_id == g.id
            )
        ).first()

        nexus_match = None
        if corr:
            nd = session.get(NexusDownload, corr.nexus_download_id)
            if nd:
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


@router.post("/correlate", response_model=CorrelateResult)
def correlate_mods(
    game_name: str, session: Session = Depends(get_session)
) -> CorrelateResult:
    game = _get_game(game_name, session)

    from chat_nexus_mod_manager.matching.correlator import correlate_game_mods

    return correlate_game_mods(game, session)
