"""Score boost for the matchers that trust a source other than the file list.

The endorsed, collection and requirement matchers know the Nexus mod is probably the right
one, so they lift the score to a fixed value. That lift is only honest when the local name
already looks like the Nexus name: from ``ON_DISK_MIN_SCORE`` up. Below it the plain name
score is kept, so the match shows as a possible one, never as installed.
"""

import logging

from sqlmodel import Session, select

from rippermod_manager.matching.correlator import compute_name_score
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModMeta, NexusModRequirement
from rippermod_manager.services.presence_service import ON_DISK_MIN_SCORE

logger = logging.getLogger(__name__)

BOOSTED_METHODS: dict[str, float] = {
    "endorsed_name": 0.85,
    "collection": 0.85,
    "requirement": 0.92,
}

# A boosted match whose name scores under this is no longer a candidate at all.
_ENTRY_MIN_SCORE = 0.55


def boosted_score(name_score: float, method: str) -> float:
    """Return the score to store: the method's floor if the name is close enough."""
    if name_score >= ON_DISK_MIN_SCORE:
        return max(name_score, BOOSTED_METHODS[method])
    return name_score


def _candidate_names(
    session: Session,
    candidates: list[ModNexusCorrelation],
    dl_map: dict[int, NexusDownload],
) -> tuple[dict[int, str], dict[int, list[str]], dict[int, set[int]]]:
    """Load, with one query each, the other names the matchers may have scored.

    Returns the ``NexusModMeta.name`` by Nexus mod id, and, from the forward requirement rows
    only (``is_reverse`` false), the ``mod_name`` values and the requiring mod ids by required
    Nexus mod id. The requirement data is only loaded for the ``requirement`` method.
    """
    nexus_ids = {
        dl.nexus_mod_id
        for c in candidates
        if (dl := dl_map.get(c.nexus_download_id)) is not None and dl.nexus_mod_id
    }
    if not nexus_ids:
        return {}, {}, {}
    meta_rows = session.exec(
        select(NexusModMeta).where(NexusModMeta.nexus_mod_id.in_(nexus_ids))  # type: ignore[attr-defined]
    ).all()
    meta_names = {m.nexus_mod_id: m.name for m in meta_rows if m.name}

    req_names: dict[int, list[str]] = {}
    requirers: dict[int, set[int]] = {}
    req_ids = {
        dl.nexus_mod_id
        for c in candidates
        if c.method == "requirement"
        and (dl := dl_map.get(c.nexus_download_id)) is not None
        and dl.nexus_mod_id
    }
    if req_ids:
        req_rows = session.exec(
            select(NexusModRequirement).where(
                NexusModRequirement.required_mod_id.in_(req_ids),  # type: ignore[union-attr]
                NexusModRequirement.is_reverse.is_(False),  # type: ignore[union-attr]
            )
        ).all()
        for r in req_rows:
            if r.required_mod_id is None:
                continue
            requirers.setdefault(r.required_mod_id, set()).add(r.nexus_mod_id)
            if r.mod_name:
                req_names.setdefault(r.required_mod_id, []).append(r.mod_name)
    return meta_names, req_names, requirers


def revalidate_boosted(
    session: Session,
    existing: list[ModNexusCorrelation],
    group_map: dict[int, ModGroup],
    dl_map: dict[int, NexusDownload],
) -> int:
    """Re-score the stored unconfirmed boosted correlations on the current names.

    A correlation saved before the boost depended on the name stays at its fixed score
    until this runs. Those whose name is under the entry threshold are deleted (and removed
    from ``existing``); the rest get the score ``boosted_score`` gives today. Returns the
    number deleted.

    A match is scored against the best of the names a matcher could have used for that Nexus
    mod: the download's name, the ``NexusModMeta`` name and, for ``requirement``, the name on
    the requirement row. Scoring only the download's name would drop matches that the matchers
    themselves found through another name.

    A ``requirement`` match is also dropped when no forward requirement row points at its Nexus
    mod from another correlated mod: that is a mod depending on the correlated one (a translation,
    an add-on), or a requirer that is no longer correlated.
    """
    candidates = [c for c in existing if not c.confirmed_by_user and c.method in BOOSTED_METHODS]
    meta_names, req_names, requirers = _candidate_names(session, candidates, dl_map)
    correlated_ids = {
        dl.nexus_mod_id for c in existing if (dl := dl_map.get(c.nexus_download_id)) is not None
    }
    deleted = 0
    for corr in candidates:
        grp = group_map.get(corr.mod_group_id)
        dl = dl_map.get(corr.nexus_download_id)
        if not grp or not dl:
            session.delete(corr)
            existing.remove(corr)
            deleted += 1
            continue
        if corr.method == "requirement" and not (
            requirers.get(dl.nexus_mod_id, set()) & (correlated_ids - {dl.nexus_mod_id})
        ):
            logger.info(
                "Dropping requirement correlation: '%s' -> '%s' (no forward requirement from "
                "another correlated mod)",
                grp.display_name,
                dl.mod_name,
            )
            session.delete(corr)
            existing.remove(corr)
            deleted += 1
            continue
        names = [dl.mod_name]
        if dl.nexus_mod_id in meta_names:
            names.append(meta_names[dl.nexus_mod_id])
        if corr.method == "requirement":
            names.extend(req_names.get(dl.nexus_mod_id, []))
        name_score = max(compute_name_score(grp.display_name, n)[0] for n in names)
        if name_score < _ENTRY_MIN_SCORE:
            logger.info(
                "Dropping boosted correlation: '%s' -> '%s' (was %s/%.2f, name now %.2f)",
                grp.display_name,
                dl.mod_name,
                corr.method,
                corr.score,
                name_score,
            )
            session.delete(corr)
            existing.remove(corr)
            deleted += 1
            continue
        new_score = boosted_score(name_score, corr.method)
        if new_score != corr.score:
            logger.info(
                "Re-scoring boosted correlation: '%s' -> '%s' (%s %.2f -> %.2f)",
                grp.display_name,
                dl.mod_name,
                corr.method,
                corr.score,
                new_score,
            )
            corr.score = new_score
            corr.reasoning = f"re-scored: name similarity {name_score:.2f}"
            session.add(corr)
    return deleted
