import logging
import re

import jellyfish
from sqlmodel import Session, select

from chat_nexus_mod_manager.matching.filename_parser import parse_mod_filename
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload
from chat_nexus_mod_manager.schemas.mod import CorrelateResult

logger = logging.getLogger(__name__)

SEPARATOR_RE = re.compile(r"[_\-.\s]+")


def normalize(s: str) -> str:
    s = SEPARATOR_RE.sub(" ", s).strip().lower()
    return s


def token_jaccard(a: str, b: str) -> float:
    tokens_a = set(normalize(a).split())
    tokens_b = set(normalize(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def compute_name_score(local_name: str, nexus_name: str) -> tuple[float, str]:
    ln = normalize(local_name)
    nn = normalize(nexus_name)

    if ln == nn:
        return 1.0, "exact"

    if ln in nn or nn in ln:
        return 0.9, "substring"

    jaccard = token_jaccard(local_name, nexus_name)
    jw = jellyfish.jaro_winkler_similarity(ln, nn)
    combined = 0.5 * jaccard + 0.5 * jw

    return round(combined, 3), "fuzzy"


def correlate_game_mods(game: Game, session: Session) -> CorrelateResult:
    groups = session.exec(select(ModGroup).where(ModGroup.game_id == game.id)).all()

    downloads = session.exec(select(NexusDownload).where(NexusDownload.game_id == game.id)).all()

    if not groups or not downloads:
        return CorrelateResult(total_groups=len(groups), matched=0, unmatched=len(groups))

    existing = session.exec(
        select(ModNexusCorrelation).where(
            ModNexusCorrelation.mod_group_id.in_([g.id for g in groups])  # type: ignore[union-attr]
        )
    ).all()
    already_matched: set[int] = set()
    for corr in existing:
        already_matched.add(corr.mod_group_id)

    nexus_id_map: dict[int, NexusDownload] = {}
    for dl in downloads:
        if dl.nexus_mod_id:
            nexus_id_map.setdefault(dl.nexus_mod_id, dl)

    matched = 0
    for group in groups:
        if group.id in already_matched:
            matched += 1
            continue

        best_score = 0.0
        best_download: NexusDownload | None = None
        best_method = ""

        # Fast path: try to match via Nexus mod ID parsed from filenames
        _ = group.files
        for f in group.files:
            parsed = parse_mod_filename(f.filename)
            if parsed.nexus_mod_id and parsed.nexus_mod_id in nexus_id_map:
                best_download = nexus_id_map[parsed.nexus_mod_id]
                best_score = 0.95
                best_method = "filename_id"
                break

        # Slow path: fuzzy name matching
        if not best_download:
            for dl in downloads:
                score, method = compute_name_score(group.display_name, dl.mod_name)
                if score > best_score:
                    best_score = score
                    best_download = dl
                    best_method = method

        if best_download and best_score >= 0.4:
            if best_score < 0.5:
                logger.info(
                    "Low-confidence match (%.2f): '%s' -> '%s' via %s",
                    best_score,
                    group.display_name,
                    best_download.mod_name,
                    best_method,
                )
            corr = ModNexusCorrelation(
                mod_group_id=group.id,  # type: ignore[arg-type]
                nexus_download_id=best_download.id,  # type: ignore[arg-type]
                score=best_score,
                method=best_method,
                reasoning=(
                    f"Matched '{group.display_name}' "
                    f"-> '{best_download.mod_name}' "
                    f"via {best_method}"
                ),
            )
            session.add(corr)
            matched += 1

    session.commit()

    try:
        from chat_nexus_mod_manager.vector.indexer import index_correlations

        index_correlations(game.id)
        logger.info("Auto-indexed correlations into vector store")
    except Exception:
        logger.warning("Failed to auto-index correlations", exc_info=True)

    return CorrelateResult(
        total_groups=len(groups),
        matched=matched,
        unmatched=len(groups) - matched,
    )
