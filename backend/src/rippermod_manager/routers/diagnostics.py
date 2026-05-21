import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from rippermod_manager.database import get_session
from rippermod_manager.services.diagnostics_service import build_diagnostics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/")
def get_diagnostics(session: Session = Depends(get_session)) -> dict[str, Any]:
    """One-click diagnostics bundle for bug reports: system info, the per-game
    mod inventory + load order + game version, and the app log tail. No secrets."""
    return build_diagnostics(session)
