"""Matches the user rejected: remembered so no scan or matcher brings them back."""

from sqlmodel import Session, col, select

from rippermod_manager.models.correlation import RejectedCorrelation
from rippermod_manager.models.mod import ModGroup


def rejected_pairs(session: Session, game_id: int) -> set[tuple[int, int]]:
    """Return the rejected ``(mod_group_id, nexus_mod_id)`` pairs of a game."""
    rows = session.exec(
        select(RejectedCorrelation.mod_group_id, RejectedCorrelation.nexus_mod_id)
        .join(ModGroup, col(ModGroup.id) == col(RejectedCorrelation.mod_group_id))
        .where(ModGroup.game_id == game_id)
    ).all()
    return {(group_id, nexus_mod_id) for group_id, nexus_mod_id in rows}


def remember_rejection(session: Session, mod_group_id: int, nexus_mod_id: int) -> None:
    """Record a rejected pair (idempotent). Does not commit."""
    exists = session.exec(
        select(RejectedCorrelation).where(
            RejectedCorrelation.mod_group_id == mod_group_id,
            RejectedCorrelation.nexus_mod_id == nexus_mod_id,
        )
    ).first()
    if not exists:
        session.add(RejectedCorrelation(mod_group_id=mod_group_id, nexus_mod_id=nexus_mod_id))


def clear_rejection(session: Session, mod_group_id: int, nexus_mod_id: int) -> None:
    """Forget a rejected pair because the user chose it again. Does not commit."""
    for row in session.exec(
        select(RejectedCorrelation).where(
            RejectedCorrelation.mod_group_id == mod_group_id,
            RejectedCorrelation.nexus_mod_id == nexus_mod_id,
        )
    ).all():
        session.delete(row)
