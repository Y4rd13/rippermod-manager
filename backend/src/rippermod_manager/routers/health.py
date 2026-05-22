import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlmodel import Session

from rippermod_manager.database import get_session
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.health import HealthIssueOut, HealthReport
from rippermod_manager.services.health_service import check_health

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/health", tags=["health"])


# Plain `def`: check_health blocks on FS + sync DB, so Starlette runs it in a threadpool.
@router.get("/", response_model=HealthReport)
def get_health(
    game_name: str,
    session: Session = Depends(get_session),
) -> HealthReport:
    """Pre-launch health scan: missing/disabled requirements, outdated mods,
    incomplete installs, and foreign/untracked files."""
    game = get_game_or_404(game_name, session)
    issues = [HealthIssueOut(**asdict(i)) for i in check_health(game, session)]
    critical = sum(1 for i in issues if i.severity == "critical")
    warning = sum(1 for i in issues if i.severity == "warning")
    info = sum(1 for i in issues if i.severity == "info")
    return HealthReport(
        issues=issues,
        critical=critical,
        warning=warning,
        info=info,
        ok=critical == 0,
    )
