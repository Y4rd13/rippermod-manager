import logging
import platform
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
from sqlmodel import Session, select

from rippermod_manager.config import settings
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod

logger = logging.getLogger(__name__)

LOG_TAIL_LINES = 500

# Defence-in-depth: mask anything in the log tail that looks like a credential,
# so a stray future log line can't leak one. The bundle is already key-free
# (httpx request-URL logging is suppressed and the key is never logged); this
# just hardens that guarantee.
_SECRET_KV = re.compile(
    r"\b(api[_-]?key|token|secret|password|authorization)(\s*[:=]\s*)\S+",
    re.IGNORECASE,
)
_URL_KEY = re.compile(r"([?&](?:key|apikey|token)=)[^&\s\"']+", re.IGNORECASE)


def _scrub_secrets(line: str) -> str:
    line = _SECRET_KV.sub(r"\1\2***", line)
    return _URL_KEY.sub(r"\1***", line)


def _redact_path(path: str | None, home: str | None) -> str | None:
    """Replace the user's home-dir prefix with ~ so the OS username doesn't leak.

    Only matches on a path-separator boundary, so a sibling home like ``/home/jo``
    never partially rewrites ``/home/john/...``.
    """
    if not path or not home:
        return path
    if path == home:
        return "~"
    if path.startswith(home + "/") or path.startswith(home + "\\"):
        return "~" + path[len(home) :]
    return path


def build_diagnostics(session: Session, *, redact: bool = False) -> dict[str, Any]:
    """Assemble a single, self-contained diagnostics bundle for bug reports.

    Read-only and offline. Contains no secrets: only system info, the per-game
    mod inventory + load order + game version, and the tail of the app log. The
    Nexus API key (kept in the OS keychain / settings) is never included. When
    ``redact`` is set, home-dir paths are anonymised to ~ so the OS username
    doesn't leak when the report is shared.
    """
    home = str(Path.home()) if redact else None
    games = list(session.exec(select(Game)).all())
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "redacted": redact,
        "system": _system_info(),
        "games": [_safe_game_diagnostics(g, session, home) for g in games],
        "log_tail": _read_log_tail(home=home),
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


def _safe_game_diagnostics(game: Game, session: Session, home: str | None) -> dict[str, Any]:
    # Best-effort: one game's failure (e.g. a detached relationship or an
    # unexpected query error) must not 500 the whole export.
    try:
        return _game_diagnostics(game, session, home)
    except Exception:
        logger.warning("Diagnostics: failed to gather for game %s", game.name, exc_info=True)
        return {"name": game.name, "error": "diagnostics unavailable"}


def _game_diagnostics(game: Game, session: Session, home: str | None) -> dict[str, Any]:
    from rippermod_manager.services.game_version import read_game_version

    mods = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()
    try:
        version = read_game_version(game.install_path, game.domain_name)
    except OSError:
        version = None
    return {
        "name": game.name,
        "domain": game.domain_name,
        "install_path": _redact_path(game.install_path, home),
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
        "load_order": _load_order(game, session, home),
    }


def _load_order(game: Game, session: Session, home: str | None) -> Any:
    from rippermod_manager.services.modlist_service import get_modlist_view

    try:
        view = get_modlist_view(game, session).model_dump(mode="json")
    except (OSError, ValueError, AttributeError):
        logger.warning("Diagnostics: load-order view failed", exc_info=True)
        return None
    if home and isinstance(view, dict) and view.get("modlist_path"):
        view["modlist_path"] = _redact_path(view["modlist_path"], home)
    return view


def _read_log_tail(lines: int = LOG_TAIL_LINES, home: str | None = None) -> list[str]:
    log_path = settings.data_dir / "logs" / "rippermod.log"
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            raw = [line.rstrip("\n") for line in deque(f, maxlen=lines)]
    except OSError:
        return []
    home_re = re.compile(re.escape(home) + r"(?=[/\\]|$)") if home else None
    out: list[str] = []
    for line in raw:
        scrubbed = _scrub_secrets(line)
        if home_re:
            scrubbed = home_re.sub("~", scrubbed)
        out.append(scrubbed)
    return out
