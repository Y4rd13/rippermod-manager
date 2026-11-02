"""Background REDmod compiles, one at a time per game (S2).

Toggle, uninstall and profile load change REDmod content without a full deploy, so
they ask for a compile here instead of running ``redMod.exe`` inside the request.
Requests that arrive while a compile runs coalesce into one more run.
``compile_lock`` is the same lock ``deploy()`` takes around its own compile, so a
deploy (and Play, which deploys first) waits for a compile in progress.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from sqlmodel import Session

from rippermod_manager import database
from rippermod_manager.models.game import Game
from rippermod_manager.schemas.deploy import RedmodDeployResult, RedmodStatus
from rippermod_manager.services.coalescing_runner import CoalescingRunner

logger = logging.getLogger(__name__)

_last: dict[int, tuple[RedmodDeployResult, datetime]] = {}
_last_guard = threading.Lock()


def _compile_job(game_id: int) -> None:
    """Run ``redMod.exe deploy`` for one game and keep its result with the time."""
    from rippermod_manager.services.vfs import deploy_service

    with Session(database.engine) as session:
        game = session.get(Game, game_id)
        if game is None:
            return
        result = deploy_service.redmod_deploy(game)
    with _last_guard:
        _last[game_id] = (result, datetime.now(UTC))
    logger.info(
        "REDmod compile for game %s: ran=%s success=%s", game_id, result.ran, result.success
    )


_runner = CoalescingRunner("redmod-compile", _compile_job)


def compile_lock(game_id: int) -> threading.Lock:
    """The per-game lock a background compile holds while it runs."""
    return _runner.lock_for(game_id)


def request_redmod_compile(game: Game) -> bool:
    """Queue a background REDmod compile for *game*; True when it was queued."""
    if game.id is None:
        return False
    return _runner.request(game.id)


def redmod_status(game_id: int) -> RedmodStatus:
    """``compiling`` while a compile runs or waits, plus the last result and its time."""
    with _last_guard:
        last = _last.get(game_id)
    return RedmodStatus(
        state="compiling" if _runner.is_busy(game_id) else "idle",
        last_result=last[0] if last else None,
        last_finished_at=last[1] if last else None,
    )
