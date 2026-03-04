"""Match unmatched mod groups using Nexus mod dependency requirements.

After correlation, matched mods' requirements point to other mods. If an
unmatched group's name matches a requirement's mod_name, we get a
high-confidence correlation with zero extra API calls.
"""

import logging

from sqlmodel import Session, select

from rippermod_manager.matching.correlator import compute_name_score
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.game import Game
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModRequirement
from rippermod_manager.schemas.mod import RequirementMatchResult
from rippermod_manager.services.nexus_helpers import upsert_nexus_mod
from rippermod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)

_NAME_THRESHOLD = 0.55
_CORRELATION_SCORE = 0.92


async def match_by_requirements(
    game: Game,
    session: Session,
    on_progress: ProgressCallback = noop_progress,
) -> RequirementMatchResult:
    """Match unmatched groups using mod requirements from already-correlated mods."""
    # 1. Get all correlated nexus_mod_ids for this game
    correlated_rows = session.exec(
        select(ModNexusCorrelation.nexus_download_id, NexusDownload.nexus_mod_id)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .where(NexusDownload.game_id == game.id)
    ).all()

    correlated_nexus_ids = {row.nexus_mod_id for row in correlated_rows}
    if not correlated_nexus_ids:
        return RequirementMatchResult(requirements_checked=0, matched=0)

    # 2. Get requirements for correlated mods where required_mod_id is set
    requirements = session.exec(
        select(NexusModRequirement).where(
            NexusModRequirement.nexus_mod_id.in_(correlated_nexus_ids),  # type: ignore[union-attr]
            NexusModRequirement.required_mod_id.is_not(None),  # type: ignore[union-attr]
            NexusModRequirement.is_external.is_(False),  # type: ignore[union-attr]
        )
    ).all()

    if not requirements:
        return RequirementMatchResult(requirements_checked=0, matched=0)

    # 3. Filter to requirements whose required_mod_id is NOT already correlated
    uncorrelated_reqs = [r for r in requirements if r.required_mod_id not in correlated_nexus_ids]

    if not uncorrelated_reqs:
        return RequirementMatchResult(requirements_checked=len(requirements), matched=0)

    # 4. Get unmatched ModGroups (no correlation)
    all_group_ids = set(
        session.exec(
            select(ModGroup.id).where(ModGroup.game_id == game.id)  # type: ignore[arg-type]
        ).all()
    )
    matched_group_ids = set(session.exec(select(ModNexusCorrelation.mod_group_id)).all())
    unmatched_group_ids = all_group_ids - matched_group_ids

    if not unmatched_group_ids:
        return RequirementMatchResult(requirements_checked=len(uncorrelated_reqs), matched=0)

    unmatched_groups = session.exec(
        select(ModGroup).where(
            ModGroup.id.in_(unmatched_group_ids)  # type: ignore[union-attr]
        )
    ).all()

    # 5. Build req map: required_mod_id -> (mod_name, requiring_mod_id)
    req_map: dict[int, tuple[str, int]] = {}
    for r in uncorrelated_reqs:
        if r.required_mod_id and r.mod_name:
            req_map.setdefault(r.required_mod_id, (r.mod_name, r.nexus_mod_id))

    on_progress(
        "requirements",
        f"Checking {len(req_map)} requirements against {len(unmatched_groups)} groups",
        97,
    )

    # 6. Match unmatched groups against requirements by name
    matched = 0
    newly_matched_groups: set[int] = set()
    newly_matched_nexus_ids: set[int] = set()

    for group in unmatched_groups:
        if group.id in newly_matched_groups:
            continue

        best_req_mod_id: int | None = None
        best_score = 0.0
        best_req_name = ""

        for req_mod_id, (req_name, _requiring_mod_id) in req_map.items():
            if req_mod_id in newly_matched_nexus_ids:
                continue

            score, _ = compute_name_score(group.display_name, req_name)
            if score >= _NAME_THRESHOLD and score > best_score:
                best_score = score
                best_req_mod_id = req_mod_id
                best_req_name = req_name

        if best_req_mod_id is None:
            continue

        # Find or create NexusDownload for the required mod
        dl = session.exec(
            select(NexusDownload).where(
                NexusDownload.game_id == game.id,
                NexusDownload.nexus_mod_id == best_req_mod_id,
            )
        ).first()

        if not dl:
            dl = upsert_nexus_mod(
                session,
                game.id,  # type: ignore[arg-type]
                game.domain_name,
                best_req_mod_id,
                {"name": best_req_name},
            )
            session.flush()

        corr = ModNexusCorrelation(
            mod_group_id=group.id,  # type: ignore[arg-type]
            nexus_download_id=dl.id,  # type: ignore[arg-type]
            score=_CORRELATION_SCORE,
            method="requirement",
            reasoning=(
                f"Matched '{group.display_name}' to requirement "
                f"'{best_req_name}' (mod {best_req_mod_id}, "
                f"name similarity {best_score:.2f})"
            ),
        )
        session.add(corr)
        newly_matched_groups.add(group.id)  # type: ignore[arg-type]
        newly_matched_nexus_ids.add(best_req_mod_id)
        matched += 1

        logger.info(
            "Requirement match: '%s' -> mod %d ('%s') score=%.2f",
            group.display_name,
            best_req_mod_id,
            best_req_name,
            best_score,
        )

    if matched:
        session.commit()
        on_progress("requirements", f"Matched {matched} mods via requirements", 98)

    return RequirementMatchResult(requirements_checked=len(req_map), matched=matched)
