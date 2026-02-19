"""Shared FastAPI dependencies used across routers."""

from fastapi import HTTPException
from sqlmodel import Session, select

from chat_nexus_mod_manager.models.game import Game


def get_game_or_404(game_name: str, session: Session) -> Game:
    """Look up a game by name, raising 404 if not found."""
    game = session.exec(select(Game).where(Game.name == game_name)).first()
    if not game:
        raise HTTPException(404, f"Game '{game_name}' not found")
    return game
