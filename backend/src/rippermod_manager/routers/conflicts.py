"""Endpoints for conflict detection: persisted engine + on-the-fly archive comparison + inbox."""

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from rippermod_manager.database import get_session
from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind, Severity
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.conflict import (
    ConflictEvidenceOut,
    ConflictSummary,
    ModRef,
    ReindexResult,
)
from rippermod_manager.schemas.conflicts import (
    ConflictSeverity,
    ConflictsOverview,
    InstalledConflictsResult,
    ModConflictDetail,
    PairwiseConflictResult,
    ResolveRequest,
    ResolveResult,
)
from rippermod_manager.services.conflict_service import (
    check_installed_conflicts,
    check_pairwise_conflict,
)
from rippermod_manager.services.conflicts.engine import ConflictEngine
from rippermod_manager.services.conflicts_inbox_service import (
    get_conflicts_overview,
    get_mod_conflict_detail,
    resolve_conflict,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conflicts"])

# ---------------------------------------------------------------------------
# Persisted engine endpoints — /games/{game_name}/conflicts/…
# ---------------------------------------------------------------------------

_engine_router = APIRouter(prefix="/games/{game_name}/conflicts")


@_engine_router.get("/summary", response_model=ConflictSummary)
def conflict_summary(
    game_name: str,
    kind: ConflictKind | None = None,
    severity: Severity | None = None,
    session: Session = Depends(get_session),
) -> ConflictSummary:
    """Return the persisted conflict report for a game.

    Optionally filter by ``kind`` and/or ``severity``.
    """
    game = get_game_or_404(game_name, session)

    stmt = select(ConflictEvidence).where(ConflictEvidence.game_id == game.id)
    if kind is not None:
        stmt = stmt.where(ConflictEvidence.kind == kind)
    if severity is not None:
        stmt = stmt.where(ConflictEvidence.severity == severity)
    rows = session.exec(stmt).all()

    # Build mod-name lookup for all referenced mod IDs
    all_mod_ids: set[int] = set()
    for row in rows:
        all_mod_ids.update(int(m) for m in row.mod_ids.split(",") if m)
        if row.winner_mod_id:
            all_mod_ids.add(row.winner_mod_id)

    mod_name_map: dict[int, str] = {}
    if all_mod_ids:
        mods = session.exec(
            select(InstalledMod).where(InstalledMod.id.in_(list(all_mod_ids)))  # type: ignore[union-attr]
        ).all()
        mod_name_map = {m.id: m.name for m in mods}  # type: ignore[misc]

    def _mod_ref(mod_id: int) -> ModRef:
        return ModRef(id=mod_id, name=mod_name_map.get(mod_id, f"Unknown (ID {mod_id})"))

    evidence_out: list[ConflictEvidenceOut] = []
    by_severity: dict[Severity, int] = {s: 0 for s in Severity}
    by_kind: dict[ConflictKind, int] = {k: 0 for k in ConflictKind}

    for row in rows:
        mod_ids = [int(m) for m in row.mod_ids.split(",") if m]
        try:
            detail = json.loads(row.detail) if row.detail else {}
        except json.JSONDecodeError:
            detail = {}
        evidence_out.append(
            ConflictEvidenceOut(
                id=row.id,  # type: ignore[arg-type]
                kind=row.kind,
                severity=row.severity,
                key=row.key,
                mods=[_mod_ref(m) for m in mod_ids],
                winner=_mod_ref(row.winner_mod_id) if row.winner_mod_id else None,
                detail=detail,
            )
        )
        by_severity[row.severity] += 1
        by_kind[row.kind] += 1

    return ConflictSummary(
        game_name=game.name,
        total_conflicts=len(evidence_out),
        by_severity=by_severity,
        by_kind=by_kind,
        evidence=evidence_out,
    )


@_engine_router.post("/reindex", response_model=ReindexResult)
def reindex_conflicts(
    game_name: str,
    session: Session = Depends(get_session),
) -> ReindexResult:
    """Trigger a full conflict re-scan for all installed mods."""
    game = get_game_or_404(game_name, session)

    start = time.perf_counter()
    engine = ConflictEngine()
    evidence = engine.run(game, session)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    by_kind: dict[ConflictKind, int] = {k: 0 for k in ConflictKind}
    for ev in evidence:
        by_kind[ev.kind] += 1

    return ReindexResult(
        conflicts_found=len(evidence),
        by_kind=by_kind,
        duration_ms=elapsed_ms,
    )


# --- Inbox endpoints (global post-install conflict visibility) ---


@_engine_router.get("/inbox", response_model=ConflictsOverview)
def inbox_overview(
    game_name: str,
    session: Session = Depends(get_session),
) -> ConflictsOverview:
    """List all file conflict summaries across installed mods."""
    game = get_game_or_404(game_name, session)
    return get_conflicts_overview(game, session)


@_engine_router.get("/inbox/{mod_id}", response_model=ModConflictDetail)
def inbox_detail(
    game_name: str,
    mod_id: int,
    session: Session = Depends(get_session),
) -> ModConflictDetail:
    """Get detailed conflict evidence for a single mod."""
    game = get_game_or_404(game_name, session)
    mod = session.get(InstalledMod, mod_id)
    if not mod or mod.game_id != game.id:
        raise HTTPException(404, "Installed mod not found")
    return get_mod_conflict_detail(game, mod, session)


@_engine_router.post("/inbox/{mod_id}/resolve", response_model=ResolveResult)
def inbox_resolve(
    game_name: str,
    mod_id: int,
    data: ResolveRequest,
    session: Session = Depends(get_session),
) -> ResolveResult:
    """Resolve conflicts by reinstalling a mod to reclaim its files."""
    game = get_game_or_404(game_name, session)
    mod = session.get(InstalledMod, mod_id)
    if not mod or mod.game_id != game.id:
        raise HTTPException(404, "Installed mod not found")
    try:
        return resolve_conflict(game, mod, session, action=data.action)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


router.include_router(_engine_router)

# ---------------------------------------------------------------------------
# On-the-fly archive comparison endpoints — /conflicts/…
# ---------------------------------------------------------------------------

_archive_router = APIRouter(prefix="/conflicts")


@_archive_router.get("/", response_model=InstalledConflictsResult)
def list_conflicts(
    game_name: str,
    severity: ConflictSeverity | None = None,
    session: Session = Depends(get_session),
) -> InstalledConflictsResult:
    """Detect file conflicts between all installed mods for a game."""
    game = get_game_or_404(game_name, session)
    return check_installed_conflicts(game, session, severity_filter=severity)


@_archive_router.get("/between", response_model=PairwiseConflictResult)
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


router.include_router(_archive_router)
