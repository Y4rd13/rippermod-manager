import logging

from fastapi import APIRouter, Depends
from sqlmodel import Session

from rippermod_manager.database import get_session
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.log_error import LogError
from rippermod_manager.services.install_service import get_file_ownership_map
from rippermod_manager.services.log_reader_service import read_log_errors

logger = logging.getLogger(__name__)

# Plain `def`: read_log_errors does blocking file I/O (reading + parsing logs),
# so Starlette runs it in a threadpool. See .claude/rules/backend.md.
router = APIRouter(prefix="/games/{game_name}/log-errors", tags=["logs"])


@router.get("/", response_model=list[LogError])
def get_log_errors(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[LogError]:
    """Recent warnings/errors parsed from the modding frameworks' log files
    (redscript, RED4ext, CET, ArchiveXL, TweakXL, Codeware)."""
    game = get_game_or_404(game_name, session)
    # Map game-relative file paths -> owning mod name so errors that name a file
    # can be attributed (best-effort) to the mod responsible.
    owners = {path: mod.name for path, mod in get_file_ownership_map(session, game.id).items()}
    return [LogError(**row) for row in read_log_errors(game.install_path, owners)]
