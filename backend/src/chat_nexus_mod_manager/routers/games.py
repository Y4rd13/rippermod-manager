from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.game import Game, GameModPath
from chat_nexus_mod_manager.schemas.game import GameCreate, GameOut

router = APIRouter(prefix="/games", tags=["games"])

CYBERPUNK_DEFAULT_PATHS = [
    ("archive/pc/mod", "Main mod archives", True),
    ("bin/x64/plugins/cyber_engine_tweaks/mods", "CET script mods", True),
    ("red4ext/plugins", "RED4ext plugins", True),
    ("r6/scripts", "Redscript mods", True),
    ("r6/tweaks", "TweakXL tweaks", True),
    ("bin/x64/plugins", "ASI/plugin loaders", True),
    ("mods", "REDmod mods", True),
]


@router.get("/", response_model=list[GameOut])
def list_games(session: Session = Depends(get_session)) -> list[Game]:
    games = session.exec(select(Game)).all()
    for game in games:
        _ = game.mod_paths
    return list(games)


@router.post("/", response_model=GameOut, status_code=201)
def create_game(data: GameCreate, session: Session = Depends(get_session)) -> Game:
    existing = session.exec(select(Game).where(Game.name == data.name)).first()
    if existing:
        raise HTTPException(400, f"Game '{data.name}' already exists")

    game = Game(
        name=data.name,
        domain_name=data.domain_name,
        install_path=data.install_path,
        os=data.os,
    )
    session.add(game)
    session.flush()

    mod_paths = data.mod_paths
    if not mod_paths and data.domain_name == "cyberpunk2077":
        for rel_path, desc, is_default in CYBERPUNK_DEFAULT_PATHS:
            session.add(
                GameModPath(
                    game_id=game.id,  # type: ignore[arg-type]
                    relative_path=rel_path,
                    description=desc,
                    is_default=is_default,
                )
            )
    else:
        for mp in mod_paths:
            session.add(
                GameModPath(
                    game_id=game.id,  # type: ignore[arg-type]
                    relative_path=mp.relative_path,
                    description=mp.description,
                    is_default=mp.is_default,
                )
            )

    session.commit()
    session.refresh(game)
    _ = game.mod_paths
    return game


@router.get("/{name}", response_model=GameOut)
def get_game(name: str, session: Session = Depends(get_session)) -> Game:
    game = session.exec(select(Game).where(Game.name == name)).first()
    if not game:
        raise HTTPException(404, f"Game '{name}' not found")
    _ = game.mod_paths
    return game


@router.delete("/{name}", status_code=204)
def delete_game(name: str, session: Session = Depends(get_session)) -> None:
    game = session.exec(select(Game).where(Game.name == name)).first()
    if not game:
        raise HTTPException(404, f"Game '{name}' not found")
    game.updated_at = datetime.utcnow()
    session.delete(game)
    session.commit()
