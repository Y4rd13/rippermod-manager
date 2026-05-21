import logging
import platform
from collections import deque
from datetime import UTC, datetime
from typing import Any

import psutil
from sqlmodel import Session, select

from rippermod_manager.config import settings
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod

logger = logging.getLogger(__name__)

LOG_TAIL_LINES = 500


def build_diagnostics(session: Session) -> dict[str, Any]:
    """Assemble a single, self-contained diagnostics bundle for bug reports.

    Read-only and offline. Contains no secrets: only system info, the per-game
    mod inventory + load order + game version, and the tail of the app log. The
    Nexus API key (kept in the OS keychain / settings) is never included.
    """
    games = list(session.exec(select(Game)).all())
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "system": _system_info(),
        "games": [_safe_game_diagnostics(g, session) for g in games],
        "log_tail": _read_log_tail(),
    }


def _system_info() -> dict[str, Any]:
    try:
        vm = psutil.virtual_memory()
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_logical": psutil.cpu_count(logical=True),
            "cpu_physical": psutil.cpu_count(logical=False),
            "ram_total_gb": round(vm.total / (1024**3), 1),
        }
    except (psutil.Error, OSError):
        logger.warning("Diagnostics: system info probe failed", exc_info=True)
        return {}


def _safe_game_diagnostics(game: Game, session: Session) -> dict[str, Any]:
    # Best-effort: one game's failure (e.g. a detached relationship or an
    # unexpected query error) must not 500 the whole export.
    try:
        return _game_diagnostics(game, session)
    except Exception:
        logger.warning("Diagnostics: failed to gather for game %s", game.name, exc_info=True)
        return {"name": game.name, "error": "diagnostics unavailable"}


def _game_diagnostics(game: Game, session: Session) -> dict[str, Any]:
    from rippermod_manager.services.game_version import read_game_version

    mods = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()
    try:
        version = read_game_version(game.install_path, game.domain_name)
    except OSError:
        version = None
    return {
        "name": game.name,
        "domain": game.domain_name,
        "install_path": game.install_path,
        "game_version": version,
        "mods": [
            {
                "name": m.name,
                "version": m.installed_version,
                "enabled": not m.disabled,
                "deployed": m.deployed,
                "nexus_mod_id": m.nexus_mod_id,
            }
            for m in mods
        ],
        "load_order": _load_order(game, session),
    }


def _load_order(game: Game, session: Session) -> Any:
    from rippermod_manager.services.modlist_service import get_modlist_view

    try:
        return get_modlist_view(game, session).model_dump(mode="json")
    except (OSError, ValueError, AttributeError):
        logger.warning("Diagnostics: load-order view failed", exc_info=True)
        return None


def _read_log_tail(lines: int = LOG_TAIL_LINES) -> list[str]:
    log_path = settings.data_dir / "logs" / "rippermod.log"
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in deque(f, maxlen=lines)]
    except OSError:
        return []
