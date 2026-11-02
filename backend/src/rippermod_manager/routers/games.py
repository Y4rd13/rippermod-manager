import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func
from sqlmodel import Session, select

from rippermod_manager.constants import CYBERPUNK_DEFAULT_PATHS, GAME_REGISTRY
from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.schemas.game import (
    GameCreate,
    GameOut,
    GameUpdate,
    GameVersion,
    ModPathCreate,
    ModPathOut,
    PathValidation,
    PathValidationRequest,
)
from rippermod_manager.services.paths import is_unc_path, resolve_mods_dir
from rippermod_manager.services.vfs.primitives import VfsError, same_volume

router = APIRouter(prefix="/games", tags=["games"])


def _validate_mods_dir(install_path: str, mods_dir: str) -> None:
    """Raise 422 if mods_dir doesn't live on the same volume as install_path.

    NTFS hardlinks (used by the VFS deploy) cannot cross volumes, so we reject
    the staging override up-front rather than failing later at deploy time.
    """
    try:
        on_same_volume = same_volume(Path(install_path), Path(mods_dir))
    except VfsError as exc:
        raise HTTPException(422, f"Cannot resolve mods_dir path: {exc}") from exc
    if not on_same_volume:
        raise HTTPException(
            422,
            (
                f"mods_dir must live on the same physical volume as the game install "
                f"({install_path}); NTFS hardlinks cannot cross volumes."
            ),
        )


def _validate_install_path(install_path: str, domain_name: str) -> None:
    """Raise 422 unless *install_path* is a local install of a registered game.

    Every later file operation (deploy, adopt, uninstall) is rooted here, so a
    network share or an arbitrary folder (e.g. ``C:\\Windows``) is refused.
    """
    game_info = GAME_REGISTRY.get(domain_name)
    if not game_info:
        raise HTTPException(422, f"Unsupported game domain: {domain_name}")
    if is_unc_path(install_path):
        raise HTTPException(422, "Network (UNC) paths are not allowed as the game install path.")
    exe_path = Path(install_path) / game_info["exe_path"]
    if not exe_path.is_file():
        raise HTTPException(
            422,
            f"{os.path.basename(game_info['exe_path'])} not found under {install_path}. "
            "Select the folder the game is installed in.",
        )


@router.get("/", response_model=list[GameOut])
def list_games(session: Session = Depends(get_session)) -> list[Game]:
    games = session.exec(select(Game)).all()
    for game in games:
        _ = game.mod_paths
    return list(games)


@router.post("/", response_model=GameOut, status_code=201)
def create_game(data: GameCreate, session: Session = Depends(get_session)) -> Game:
    _validate_install_path(data.install_path, data.domain_name)
    normalized_mods_dir = (data.mods_dir or "").strip() or None
    if normalized_mods_dir:
        _validate_mods_dir(data.install_path, normalized_mods_dir)

    existing = session.exec(select(Game).where(Game.name == data.name)).first()
    if existing:
        # Never repoint an existing game silently: the client updates it with PATCH.
        raise HTTPException(409, f"Game '{data.name}' already exists")

    game = Game(
        name=data.name,
        domain_name=data.domain_name,
        install_path=data.install_path,
        mods_dir=normalized_mods_dir,
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


@router.patch("/{name}", response_model=GameOut)
def update_game(name: str, data: GameUpdate, session: Session = Depends(get_session)) -> Game:
    game = session.exec(select(Game).where(Game.name == name)).first()
    if not game:
        raise HTTPException(404, f"Game '{name}' not found")

    fields = data.model_fields_set
    install_path = game.install_path
    if "install_path" in fields and data.install_path is not None:
        install_path = data.install_path
        _validate_install_path(install_path, game.domain_name)
    mods_dir = game.mods_dir
    if "mods_dir" in fields:
        mods_dir = (data.mods_dir or "").strip() or None
    if mods_dir and ("mods_dir" in fields or install_path != game.install_path):
        _validate_mods_dir(install_path, mods_dir)

    # Installed mods live in the staging folder; moving it would orphan them.
    if (
        fields & {"install_path", "mods_dir"}
        and Path(resolve_mods_dir(install_path, mods_dir)).resolve()
        != Path(resolve_mods_dir(game.install_path, game.mods_dir)).resolve()
    ):
        installed = session.exec(
            select(func.count()).select_from(InstalledMod).where(InstalledMod.game_id == game.id)
        ).one()
        if installed:
            raise HTTPException(
                409,
                f"Uninstall your mods before changing the staging folder ({installed} installed).",
            )

    if fields & {"install_path", "mods_dir"}:
        game.install_path = install_path
        game.mods_dir = mods_dir
        game.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(game)

    _ = game.mod_paths
    return game


_BAD_MOD_PATH = "Folder must be a relative path inside the game directory."


def _normalize_mod_path(install_path: str, relative_path: str) -> str:
    """Return *relative_path* as ``a/b/c``, or raise 422 unless it stays inside the game.

    Refused: empty or ``.``, a NUL byte, absolute, with a drive (``C:/x``, ``C:x``), UNC, with a
    ``..`` part, or resolving (symlinks followed) outside ``install_path`` or onto it.
    The folder itself may not exist yet.
    """
    raw = relative_path.strip()
    if not raw or "\x00" in raw or is_unc_path(raw):
        raise HTTPException(422, _BAD_MOD_PATH)
    rel = raw.replace("\\", "/").rstrip("/")
    win = PureWindowsPath(rel)
    if not rel or PurePosixPath(rel).is_absolute() or win.drive or win.is_absolute():
        raise HTTPException(422, _BAD_MOD_PATH)
    parts = PurePosixPath(rel).parts
    if ".." in parts:
        raise HTTPException(422, _BAD_MOD_PATH)
    parts = tuple(p for p in parts if p != ".")
    if not parts:
        raise HTTPException(422, _BAD_MOD_PATH)
    normalized = "/".join(parts)
    root = Path(install_path).resolve()
    target = (root / normalized).resolve()
    if root not in target.parents:
        raise HTTPException(422, _BAD_MOD_PATH)
    return normalized


def _game_or_404(name: str, session: Session) -> Game:
    game = session.exec(select(Game).where(Game.name == name)).first()
    if not game:
        raise HTTPException(404, f"Game '{name}' not found")
    return game


def _mod_paths_out(game: Game, session: Session) -> list[ModPathOut]:
    rows = session.exec(
        select(GameModPath).where(GameModPath.game_id == game.id).order_by(GameModPath.id)  # type: ignore[arg-type]
    ).all()
    return [
        ModPathOut(
            id=r.id,  # type: ignore[arg-type]
            relative_path=r.relative_path,
            description=r.description,
            is_default=r.is_default,
        )
        for r in rows
    ]


@router.get("/{name}/mod-paths", response_model=list[ModPathOut])
def list_mod_paths(name: str, session: Session = Depends(get_session)) -> list[ModPathOut]:
    """The folders the scanner reads for this game, relative to its install path."""
    return _mod_paths_out(_game_or_404(name, session), session)


@router.post("/{name}/mod-paths", response_model=list[ModPathOut], status_code=201)
def add_mod_path(
    name: str, data: ModPathCreate, session: Session = Depends(get_session)
) -> list[ModPathOut]:
    """Add a scanned folder; it applies on the next scan. Returns the whole list."""
    game = _game_or_404(name, session)
    rel = _normalize_mod_path(game.install_path, data.relative_path)
    existing = session.exec(select(GameModPath).where(GameModPath.game_id == game.id)).all()
    key = rel.casefold()
    if any(e.relative_path.replace("\\", "/").strip("/").casefold() == key for e in existing):
        raise HTTPException(409, "This folder is already scanned.")
    session.add(
        GameModPath(
            game_id=game.id,  # type: ignore[arg-type]
            relative_path=rel,
            description=data.description.strip(),
            is_default=False,
        )
    )
    session.commit()
    return _mod_paths_out(game, session)


@router.delete("/{name}/mod-paths/{path_id}", status_code=204)
def remove_mod_path(name: str, path_id: int, session: Session = Depends(get_session)) -> None:
    """Stop scanning one folder. Files already scanned under it stay listed."""
    game = _game_or_404(name, session)
    row = session.get(GameModPath, path_id)
    if row is None or row.game_id != game.id:
        raise HTTPException(404, "Scanned folder not found")
    session.delete(row)
    session.commit()


@router.post("/{name}/mod-paths/reset", response_model=list[ModPathOut])
def reset_mod_paths(name: str, session: Session = Depends(get_session)) -> list[ModPathOut]:
    """Replace the scanned folders with the game's defaults (none for other games)."""
    game = _game_or_404(name, session)
    session.exec(delete(GameModPath).where(GameModPath.game_id == game.id))  # type: ignore[arg-type]
    if game.domain_name == "cyberpunk2077":
        for rel_path, desc, is_default in CYBERPUNK_DEFAULT_PATHS:
            session.add(
                GameModPath(
                    game_id=game.id,  # type: ignore[arg-type]
                    relative_path=rel_path,
                    description=desc,
                    is_default=is_default,
                )
            )
    session.commit()
    return _mod_paths_out(game, session)


@router.get("/{name}/version", response_model=GameVersion)
def get_game_version(name: str, session: Session = Depends(get_session)) -> GameVersion:
    game = session.exec(select(Game).where(Game.name == name)).first()
    if not game:
        raise HTTPException(404, f"Game '{name}' not found")

    game_info = GAME_REGISTRY.get(game.domain_name)
    if not game_info:
        raise HTTPException(
            422, f"Version detection not supported for game type '{game.domain_name}'"
        )

    from rippermod_manager.services.game_version import read_game_version

    version = read_game_version(game.install_path, game.domain_name)
    return GameVersion(version=version, exe_path=game_info["exe_path"])


@router.delete("/{name}", status_code=204)
def delete_game(name: str, session: Session = Depends(get_session)) -> None:
    game = session.exec(select(Game).where(Game.name == name)).first()
    if not game:
        raise HTTPException(404, f"Game '{name}' not found")

    game_id = game.id

    from rippermod_manager.models.activity import ActivityLog
    from rippermod_manager.models.archive_index import ArchiveEntryIndex
    from rippermod_manager.models.collection import InstalledCollection
    from rippermod_manager.models.conflict import ConflictEvidence
    from rippermod_manager.models.correlation import ModNexusCorrelation, RejectedCorrelation
    from rippermod_manager.models.download import DownloadJob
    from rippermod_manager.models.install import (
        ArchiveNexusLink,
        DeployJournalEntry,
        DisplacedFile,
        InstalledMod,
        InstalledModFile,
    )
    from rippermod_manager.models.load_order import LoadOrderPreference
    from rippermod_manager.models.mod import ModFile, ModGroup, ModGroupAlias
    from rippermod_manager.models.nexus import NexusDownload
    from rippermod_manager.models.profile import Profile, ProfileEntry

    # Delete in FK-safe order: children before parents
    profile_ids = [p.id for p in session.exec(select(Profile).where(Profile.game_id == game_id))]
    if profile_ids:
        session.exec(delete(ProfileEntry).where(ProfileEntry.profile_id.in_(profile_ids)))  # type: ignore[union-attr]
    session.exec(delete(Profile).where(Profile.game_id == game_id))  # type: ignore[call-overload]

    # Rows that reference installed_mods
    session.exec(delete(LoadOrderPreference).where(LoadOrderPreference.game_id == game_id))  # type: ignore[call-overload]
    session.exec(delete(ArchiveEntryIndex).where(ArchiveEntryIndex.game_id == game_id))  # type: ignore[call-overload]
    session.exec(delete(ConflictEvidence).where(ConflictEvidence.game_id == game_id))  # type: ignore[call-overload]

    installed_ids = [
        m.id for m in session.exec(select(InstalledMod).where(InstalledMod.game_id == game_id))
    ]
    if installed_ids:
        session.exec(
            delete(InstalledModFile).where(InstalledModFile.installed_mod_id.in_(installed_ids))
        )  # type: ignore[union-attr]
    session.exec(delete(InstalledMod).where(InstalledMod.game_id == game_id))  # type: ignore[call-overload]

    # download_jobs and installed_mods reference installed_collections
    session.exec(delete(DownloadJob).where(DownloadJob.game_id == game_id))  # type: ignore[call-overload]
    session.exec(delete(InstalledCollection).where(InstalledCollection.game_id == game_id))  # type: ignore[call-overload]

    group_ids = [g.id for g in session.exec(select(ModGroup).where(ModGroup.game_id == game_id))]
    download_ids = [
        d.id for d in session.exec(select(NexusDownload).where(NexusDownload.game_id == game_id))
    ]
    if group_ids or download_ids:
        session.exec(
            delete(ModNexusCorrelation).where(
                ModNexusCorrelation.mod_group_id.in_(group_ids)  # type: ignore[attr-defined]
                | ModNexusCorrelation.nexus_download_id.in_(download_ids)  # type: ignore[attr-defined]
            )
        )
    if group_ids:
        session.exec(
            delete(RejectedCorrelation).where(RejectedCorrelation.mod_group_id.in_(group_ids))  # type: ignore[attr-defined]
        )
        session.exec(delete(ModGroupAlias).where(ModGroupAlias.mod_group_id.in_(group_ids)))  # type: ignore[union-attr]
        session.exec(delete(ModFile).where(ModFile.mod_group_id.in_(group_ids)))  # type: ignore[union-attr]
    session.exec(delete(ModGroup).where(ModGroup.game_id == game_id))  # type: ignore[call-overload]

    session.exec(delete(NexusDownload).where(NexusDownload.game_id == game_id))  # type: ignore[call-overload]

    session.exec(delete(ArchiveNexusLink).where(ArchiveNexusLink.game_id == game_id))  # type: ignore[call-overload]
    session.exec(delete(DeployJournalEntry).where(DeployJournalEntry.game_id == game_id))  # type: ignore[call-overload]
    session.exec(delete(DisplacedFile).where(DisplacedFile.game_id == game_id))  # type: ignore[call-overload]
    session.exec(delete(ActivityLog).where(ActivityLog.game_id == game_id))  # type: ignore[call-overload]

    session.delete(game)
    session.commit()
