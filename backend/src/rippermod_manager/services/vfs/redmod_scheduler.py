"""Background REDmod compiles, one at a time per game (S2).

Toggle, uninstall and profile load change REDmod content without a full deploy, so
they ask for a compile here instead of running ``redMod.exe`` inside the request.
Requests that arrive while a compile runs coalesce into one more run.
``compile_lock`` is the same lock ``deploy()`` takes around its own compile, so a
deploy (and Play, which deploys first) waits for a compile in progress.
A compile requested before an undeploy is skipped, so it cannot write the REDmod
cache that undeploy removed back into the game dir.
"""

from __future__ import annotations

import itertools
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

# Positions on one shared counter, not clock times: two events in the same clock tick
# (Windows' monotonic clock advances in ~16 ms steps) must still be ordered.
_sequence = itertools.count(1)
_last_request_at: dict[int, int] = {}
_undeployed_at: dict[int, int] = {}

_UNDEPLOYED_REASON = "Game was undeployed after this compile was requested"


def _compile_job(game_id: int) -> None:
    """Run ``redMod.exe deploy`` for one game and keep its result with the time."""
    from rippermod_manager.services.vfs import deploy_service

    with _last_guard:
        undeployed = _undeployed_at.get(game_id, 0) >= _last_request_at.get(game_id, 0) > 0
    if undeployed:
        with _last_guard:
            _last[game_id] = (
                RedmodDeployResult(ran=False, skipped_reason=_UNDEPLOYED_REASON),
                datetime.now(UTC),
            )
        logger.info("REDmod compile for game %s skipped: undeployed after the request", game_id)
        return

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
    with _last_guard:
        _last_request_at[game.id] = next(_sequence)
    return _runner.request(game.id)


def mark_undeployed(game_id: int) -> None:
    """Record that *game_id* was undeployed; compiles requested before now are skipped."""
    with _last_guard:
        _undeployed_at[game_id] = next(_sequence)


def redmod_status(game_id: int) -> RedmodStatus:
    """``compiling`` while a compile runs or waits, plus the last result and its time."""
    with _last_guard:
        last = _last.get(game_id)
    return RedmodStatus(
        state="compiling" if _runner.is_busy(game_id) else "idle",
        last_result=last[0] if last else None,
        last_finished_at=last[1] if last else None,
    )
