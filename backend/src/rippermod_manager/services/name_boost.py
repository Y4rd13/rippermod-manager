"""Score boost for the matchers that trust a source other than the file list.

The endorsed, collection and requirement matchers know the Nexus mod is probably the right
one, so they lift the score to a fixed value. That lift is only honest when the local name
already looks like the Nexus name: from ``ON_DISK_MIN_SCORE`` up. Below it the plain name
score is kept, so the match shows as a possible one, never as installed.
"""

import logging

from sqlmodel import Session

from rippermod_manager.matching.correlator import compute_name_score
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload
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
    """
    deleted = 0
    for corr in list(existing):
        if corr.confirmed_by_user or corr.method not in BOOSTED_METHODS:
            continue
        grp = group_map.get(corr.mod_group_id)
        dl = dl_map.get(corr.nexus_download_id)
        if not grp or not dl:
            session.delete(corr)
            existing.remove(corr)
            deleted += 1
            continue
        name_score, _ = compute_name_score(grp.display_name, dl.mod_name)
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
