import os
from datetime import UTC, datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.game import Game, GameModPath
from chat_nexus_mod_manager.schemas.game import (
    GameCreate,
    GameOut,
    PathValidation,
    PathValidationRequest,
)

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


class GameRegistryEntry(TypedDict):
    exe_path: str
    mod_paths: list[tuple[str, str, bool]]


GAME_REGISTRY: dict[str, GameRegistryEntry] = {
    "cyberpunk2077": {
        "exe_path": os.path.join("bin", "x64", "Cyberpunk2077.exe"),
        "mod_paths": CYBERPUNK_DEFAULT_PATHS,
    },
}


@router.get("/", response_model=list[GameOut])
def list_games(session: Session = Depends(get_session)) -> list[Game]:
    games = session.exec(select(Game)).all()
    for game in games:
        _ = game.mod_paths
    return list(games)


@router.post("/", response_model=GameOut, status_code=201)
def create_game(
    data: GameCreate, response: Response, session: Session = Depends(get_session)
) -> Game:
    existing = session.exec(select(Game).where(Game.name == data.name)).first()
    if existing:
        existing.install_path = data.install_path
        existing.domain_name = data.domain_name
        existing.os = data.os
        existing.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(existing)
        _ = existing.mod_paths
        response.status_code = 200
        return existing

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


@router.post("/validate-path", response_model=PathValidation)
def validate_game_path(data: PathValidationRequest) -> PathValidation:
    install_path = data.install_path
    game_info = GAME_REGISTRY.get(data.domain_name)

    if not game_info:
        return PathValidation(
            valid=False,
            path=install_path,
            found_exe=False,
            found_mod_dirs=[],
            warning=f"Unknown game domain: {data.domain_name}",
        )

    exe_path = os.path.join(install_path, game_info["exe_path"])
    found_exe = os.path.isfile(exe_path)

    found_mod_dirs: list[str] = []
    for rel_path, _desc, _default in game_info["mod_paths"]:
        full_path = os.path.join(install_path, rel_path)
        if os.path.isdir(full_path):
            found_mod_dirs.append(rel_path)

    valid = found_exe
    warning = ""
    if found_exe and not found_mod_dirs:
        warning = (
            "Game executable found but no mod directories detected. Mods may not be installed yet."
        )
    elif not found_exe:
        exe_name = os.path.basename(game_info["exe_path"])
        warning = f"{exe_name} not found. Please verify the installation path."

    return PathValidation(
        valid=valid,
        path=install_path,
        found_exe=found_exe,
        found_mod_dirs=found_mod_dirs,
        warning=warning,
    )


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

    game_id = game.id

    from chat_nexus_mod_manager.vector.indexer import delete_game_vectors

    delete_game_vectors(game_id)

    from chat_nexus_mod_manager.models.install import InstalledMod, InstalledModFile
    from chat_nexus_mod_manager.models.mod import ModFile, ModGroup, ModGroupAlias
    from chat_nexus_mod_manager.models.nexus import NexusDownload
    from chat_nexus_mod_manager.models.profile import Profile, ProfileEntry

    # Delete in FK-safe order: children before parents
    profile_ids = [p.id for p in session.exec(select(Profile).where(Profile.game_id == game_id))]
    if profile_ids:
        session.exec(delete(ProfileEntry).where(ProfileEntry.profile_id.in_(profile_ids)))  # type: ignore[union-attr]
    session.exec(delete(Profile).where(Profile.game_id == game_id))  # type: ignore[call-overload]

    installed_ids = [
        m.id for m in session.exec(select(InstalledMod).where(InstalledMod.game_id == game_id))
    ]
    if installed_ids:
        session.exec(
            delete(InstalledModFile).where(InstalledModFile.installed_mod_id.in_(installed_ids))
        )  # type: ignore[union-attr]
    session.exec(delete(InstalledMod).where(InstalledMod.game_id == game_id))  # type: ignore[call-overload]

    group_ids = [g.id for g in session.exec(select(ModGroup).where(ModGroup.game_id == game_id))]
    if group_ids:
        session.exec(delete(ModGroupAlias).where(ModGroupAlias.mod_group_id.in_(group_ids)))  # type: ignore[union-attr]
        session.exec(delete(ModFile).where(ModFile.mod_group_id.in_(group_ids)))  # type: ignore[union-attr]
    session.exec(delete(ModGroup).where(ModGroup.game_id == game_id))  # type: ignore[call-overload]

    session.exec(delete(NexusDownload).where(NexusDownload.game_id == game_id))  # type: ignore[call-overload]

    session.delete(game)
    session.commit()
