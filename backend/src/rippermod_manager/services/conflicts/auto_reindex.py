"""Automatic conflict reindex in the background (S3).

Scan, install, uninstall, toggle and profile load ask for a reindex here. Each
request waits ``REINDEX_DEBOUNCE_S`` seconds without new requests, then one run
happens per game at a time; requests during a run coalesce into one more.
"""

from __future__ import annotations

import logging

from sqlmodel import Session

from rippermod_manager import database
from rippermod_manager.models.game import Game
from rippermod_manager.services.coalescing_runner import CoalescingRunner

logger = logging.getLogger(__name__)

REINDEX_DEBOUNCE_S = 2.0


def _reindex_job(game_id: int) -> None:
    """Reindex one game's conflicts with its own session."""
    from rippermod_manager.services.conflicts.engine import reindex_game

    with Session(database.engine) as session:
        game = session.get(Game, game_id)
        if game is None:
            return
        reindex_game(game, session)


_runner = CoalescingRunner("conflict-reindex", _reindex_job, debounce_s=REINDEX_DEBOUNCE_S)


def request_conflict_reindex(game_id: int | None) -> None:
    """Ask for a background conflict reindex of *game_id* (ignored when None)."""
    if game_id is None:
        return
    _runner.request(game_id)
