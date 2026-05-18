"""Endpoints for archive load-order inspection and conflict resolution."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.load_order import (
    AutoSortApplyResult,
    AutoSortPreview,
    BatchPreferencesRequest,
    BatchPreferencesResult,
    LoadOrderResult,
    ModlistViewResult,
    PreferModRequest,
    PreferModResult,
    RemovePreferenceResult,
    ResetPreferencesResult,
)
from rippermod_manager.services.auto_sort_service import compute_auto_sort
from rippermod_manager.services.load_order import get_archive_load_order
from rippermod_manager.services.modlist_service import (
    add_preferences,
    apply_preferences_batch,
    generate_modlist,
    get_modlist_view,
    remove_all_preferences,
    remove_preference,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/load-order", tags=["load-order"])


def _validate_prefer_request(
    game_name: str,
    data: PreferModRequest,
    session: Session,
) -> tuple[Game, InstalledMod, list[InstalledMod]]:
    """Validate and return ``(game, winner_mod, loser_mods)``."""
    game = get_game_or_404(game_name, session)

    winner = session.get(InstalledMod, data.winner_mod_id)
    if not winner or winner.game_id != game.id:
        raise HTTPException(404, f"Winner mod {data.winner_mod_id} not found for this game")
    if winner.disabled:
        raise HTTPException(400, f"Winner mod '{winner.name}' is disabled")

    if not data.loser_mod_ids:
        raise HTTPException(400, "At least one loser_mod_id is required")

    loser_mods: list[InstalledMod] = []
    for loser_id in data.loser_mod_ids:
        if loser_id == data.winner_mod_id:
            raise HTTPException(400, "winner_mod_id and loser_mod_id must differ")
        loser = session.get(InstalledMod, loser_id)
        if not loser or loser.game_id != game.id:
            raise HTTPException(404, f"Loser mod {loser_id} not found for this game")
        if loser.disabled:
            raise HTTPException(400, f"Loser mod '{loser.name}' is disabled")
        loser_mods.append(loser)

    return game, winner, loser_mods


@router.get("/", response_model=LoadOrderResult)
async def load_order(
    game_name: str,
    session: Session = Depends(get_session),
) -> LoadOrderResult:
    """Return the full archive load order and detected conflicts."""
    game = get_game_or_404(game_name, session)
    return get_archive_load_order(game, session)


@router.post("/prefer/preview", response_model=PreferModResult)
async def prefer_preview(
    game_name: str,
    data: PreferModRequest,
    session: Session = Depends(get_session),
) -> PreferModResult:
    """Dry-run: show what preferences would be added without writing modlist.txt."""
    game, winner, loser_mods = _validate_prefer_request(game_name, data, session)
    modlist = generate_modlist(game, session)
    loser_names = [m.name for m in loser_mods]
    return PreferModResult(
        success=True,
        message=(
            f"Will prefer '{winner.name}' over {', '.join(repr(n) for n in loser_names)}. "
            f"modlist.txt will be updated ({len(modlist)} entries currently)."
        ),
        preferences_added=len(loser_mods),
        modlist_entries=len(modlist),
        dry_run=True,
    )


@router.post("/prefer", response_model=PreferModResult)
async def prefer(
    game_name: str,
    data: PreferModRequest,
    session: Session = Depends(get_session),
) -> PreferModResult:
    """Add load-order preferences and write modlist.txt."""
    game, winner, loser_mods = _validate_prefer_request(game_name, data, session)
    loser_ids = [m.id for m in loser_mods]  # type: ignore[misc]
    added = add_preferences(game.id, data.winner_mod_id, loser_ids, game, session)  # type: ignore[arg-type]
    modlist = generate_modlist(game, session)
    loser_names = [m.name for m in loser_mods]
    return PreferModResult(
        success=True,
        message=(
            f"Preferred '{winner.name}' over {', '.join(repr(n) for n in loser_names)}. "
            f"{added} preference(s) added, modlist.txt has {len(modlist)} entries."
        ),
        preferences_added=added,
        modlist_entries=len(modlist),
        dry_run=False,
    )


@router.get("/modlist", response_model=ModlistViewResult)
async def modlist_view(
    game_name: str,
    session: Session = Depends(get_session),
) -> ModlistViewResult:
    """Return ordered mod groups and preferences for the Load Order view."""
    game = get_game_or_404(game_name, session)
    return get_modlist_view(game, session)


@router.delete("/preferences", response_model=ResetPreferencesResult)
async def reset_preferences(
    game_name: str,
    session: Session = Depends(get_session),
) -> ResetPreferencesResult:
    """Remove all load-order preferences for a game."""
    game = get_game_or_404(game_name, session)
    removed = remove_all_preferences(game.id, game, session)  # type: ignore[arg-type]
    modlist = generate_modlist(game, session)
    return ResetPreferencesResult(
        removed_count=removed,
        modlist_entries=len(modlist),
        message=f"Removed {removed} preference(s), modlist.txt has {len(modlist)} entries.",
    )


def _validate_pair_mod_ids(
    game: Game,
    pairs: list,
    session: Session,
) -> None:
    """Ensure every mod_id referenced in pairs belongs to this game."""
    referenced: set[int] = set()
    for pair in pairs:
        referenced.add(pair.winner_mod_id)
        referenced.add(pair.loser_mod_id)
    if not referenced:
        return
    found = session.exec(
        select(InstalledMod.id).where(
            InstalledMod.id.in_(referenced),  # type: ignore[union-attr]
            InstalledMod.game_id == game.id,
        )
    ).all()
    found_set = set(found)
    missing = referenced - found_set
    if missing:
        raise HTTPException(
            404,
            f"Mod ID(s) not found for this game: {sorted(missing)}",
        )


@router.post("/preferences/batch", response_model=BatchPreferencesResult)
async def preferences_batch(
    game_name: str,
    data: BatchPreferencesRequest,
    session: Session = Depends(get_session),
) -> BatchPreferencesResult:
    """Apply add + remove of multiple preferences in one transaction.

    Used by the drag-and-drop reorder UI: a single drop translates to a minimal
    pairwise diff that's applied atomically and triggers exactly one modlist.txt
    write.
    """
    game = get_game_or_404(game_name, session)

    if not data.add and not data.remove:
        modlist = generate_modlist(game, session)
        return BatchPreferencesResult(
            success=True,
            message="No changes requested.",
            added=0,
            removed=0,
            modlist_entries=len(modlist),
        )

    _validate_pair_mod_ids(game, data.add + data.remove, session)

    added, removed = apply_preferences_batch(
        game.id,  # type: ignore[arg-type]
        [(p.winner_mod_id, p.loser_mod_id) for p in data.add],
        [(p.winner_mod_id, p.loser_mod_id) for p in data.remove],
        game,
        session,
    )
    modlist = generate_modlist(game, session)
    return BatchPreferencesResult(
        success=True,
        message=(
            f"Applied batch: +{added} added, -{removed} removed, "
            f"modlist.txt has {len(modlist)} entries."
        ),
        added=added,
        removed=removed,
        modlist_entries=len(modlist),
    )


@router.post("/auto-sort/preview", response_model=AutoSortPreview)
async def auto_sort_preview(
    game_name: str,
    session: Session = Depends(get_session),
) -> AutoSortPreview:
    """Compute (but do not apply) a conflict-aware auto-sort plan."""
    game = get_game_or_404(game_name, session)
    return compute_auto_sort(game, session)


@router.post("/auto-sort/apply", response_model=AutoSortApplyResult)
async def auto_sort_apply(
    game_name: str,
    session: Session = Depends(get_session),
) -> AutoSortApplyResult:
    """Re-compute the auto-sort plan and apply it as preferences."""
    game = get_game_or_404(game_name, session)
    plan = compute_auto_sort(game, session)
    if not plan.proposed_add and not plan.proposed_remove:
        modlist = generate_modlist(game, session)
        return AutoSortApplyResult(
            success=True,
            message=plan.rationale,
            added=0,
            removed=0,
            modlist_entries=len(modlist),
        )

    added, removed = apply_preferences_batch(
        game.id,  # type: ignore[arg-type]
        [(p.winner_mod_id, p.loser_mod_id) for p in plan.proposed_add],
        [(p.winner_mod_id, p.loser_mod_id) for p in plan.proposed_remove],
        game,
        session,
    )
    modlist = generate_modlist(game, session)
    return AutoSortApplyResult(
        success=True,
        message=(
            f"Auto-sort applied: +{added} preference(s), -{removed} reversed. "
            f"modlist.txt has {len(modlist)} entries."
        ),
        added=added,
        removed=removed,
        modlist_entries=len(modlist),
    )


@router.delete(
    "/preferences/{winner_mod_id}/{loser_mod_id}",
    response_model=RemovePreferenceResult,
)
async def delete_preference(
    game_name: str,
    winner_mod_id: int,
    loser_mod_id: int,
    session: Session = Depends(get_session),
) -> RemovePreferenceResult:
    """Remove a single load-order preference."""
    game = get_game_or_404(game_name, session)
    removed = remove_preference(game.id, winner_mod_id, loser_mod_id, game, session)  # type: ignore[arg-type]
    if not removed:
        raise HTTPException(404, "Preference not found")
    modlist = generate_modlist(game, session)
    return RemovePreferenceResult(
        success=True,
        message=f"Preference removed, modlist.txt has {len(modlist)} entries.",
        modlist_entries=len(modlist),
    )
