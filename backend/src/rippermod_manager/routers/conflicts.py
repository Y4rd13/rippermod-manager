"""Endpoints for installed-vs-installed mod conflict detection."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from rippermod_manager.database import get_session
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.conflicts import (
    ConflictSeverity,
    InstalledConflictsResult,
    PairwiseConflictResult,
)
from rippermod_manager.services.conflict_service import (
    check_installed_conflicts,
    check_pairwise_conflict,
)

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


@router.get("/", response_model=InstalledConflictsResult)
def list_conflicts(
    game_name: str,
    severity: ConflictSeverity | None = None,
    session: Session = Depends(get_session),
) -> InstalledConflictsResult:
    """Detect file conflicts between all installed mods for a game."""
    game = get_game_or_404(game_name, session)
    return check_installed_conflicts(game, session, severity_filter=severity)


@router.get("/between", response_model=PairwiseConflictResult)
def between_conflicts(
    game_name: str,
    mod_a: int,
    mod_b: int,
    session: Session = Depends(get_session),
) -> PairwiseConflictResult:
    """Compare two specific installed mods for file conflicts."""
    game = get_game_or_404(game_name, session)

    installed_a = session.get(InstalledMod, mod_a)
    if not installed_a or installed_a.game_id != game.id:
        raise HTTPException(404, f"Installed mod {mod_a} not found")
    installed_b = session.get(InstalledMod, mod_b)
    if not installed_b or installed_b.game_id != game.id:
        raise HTTPException(404, f"Installed mod {mod_b} not found")

    if not installed_a.source_archive or not installed_b.source_archive:
        missing = []
        if not installed_a.source_archive:
            missing.append(installed_a.name)
        if not installed_b.source_archive:
            missing.append(installed_b.name)
        raise HTTPException(
            422,
            f"Source archive unavailable for: {', '.join(missing)}",
        )

    try:
        return check_pairwise_conflict(game, installed_a, installed_b)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
