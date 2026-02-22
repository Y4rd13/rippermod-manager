import logging
import re

import jellyfish
from sqlmodel import Session, select

from chat_nexus_mod_manager.matching.filename_parser import parse_mod_filename
from chat_nexus_mod_manager.matching.normalization import (
    SEPARATOR_RE,
    split_camel,
    strip_ordering_prefix,
)
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.mod import ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload
from chat_nexus_mod_manager.schemas.mod import CorrelateResult

logger = logging.getLogger(__name__)
# Characters that filesystem paths often strip (apostrophes, quotes, parens)
PUNCTUATION_RE = re.compile(r"['\"\(\)]+")


def normalize(s: str) -> str:
    s = strip_ordering_prefix(s)
    s = split_camel(s)
    s = PUNCTUATION_RE.sub("", s)
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
    if jaccard == 0.0:
        return 0.0, "fuzzy"

    jw = jellyfish.jaro_winkler_similarity(ln, nn)
    combined = 0.5 * jaccard + 0.5 * jw

    return round(combined, 3), "fuzzy"


def _dedup_correlations(groups: list[ModGroup], session: Session) -> int:
    """Remove duplicate correlations pointing to the same nexus_mod_id.

    When multiple groups correlate to the same Nexus mod, keep only the
    correlation with the highest score.  Tie-break by group file count.
    """
    group_ids = [g.id for g in groups]
    if not group_ids:
        return 0

    all_corr = session.exec(
        select(ModNexusCorrelation, NexusDownload)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .where(
            ModNexusCorrelation.mod_group_id.in_(group_ids)  # type: ignore[union-attr]
        )
    ).all()

    # Group correlations by nexus_mod_id
    by_nexus: dict[int, list[tuple[ModNexusCorrelation, NexusDownload]]] = {}
    for corr, dl in all_corr:
        by_nexus.setdefault(dl.nexus_mod_id, []).append((corr, dl))

    group_file_counts: dict[int, int] = {g.id: len(g.files) for g in groups if g.id is not None}

    purged = 0
    for nexus_id, entries in by_nexus.items():
        if len(entries) <= 1:
            continue

        # Sort: highest score first, then most files
        entries.sort(
            key=lambda e: (e[0].score, group_file_counts.get(e[0].mod_group_id, 0)),
            reverse=True,
        )

        # Keep first (best), delete rest
        for corr, _dl in entries[1:]:
            if corr.confirmed_by_user:
                continue
            logger.info(
                "Dedup: removing duplicate correlation group=%d -> nexus=%d (score=%.2f)",
                corr.mod_group_id,
                nexus_id,
                corr.score,
            )
            session.delete(corr)
            purged += 1

    if purged:
        logger.info("Dedup: removed %d duplicate correlations", purged)
    return purged


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

    # Re-validate name-based correlations: NexusDownload names may have
    # changed since the correlation was created (sync updates mod_name).
    # Purge stale ones so they get re-evaluated with current names.
    _NAME_METHODS = {"exact", "substring", "fuzzy"}
    dl_map: dict[int, NexusDownload] = {dl.id: dl for dl in downloads if dl.id is not None}
    group_map: dict[int, ModGroup] = {g.id: g for g in groups if g.id is not None}
    purged = 0
    for corr in list(existing):
        if corr.confirmed_by_user or corr.method not in _NAME_METHODS:
            continue
        grp = group_map.get(corr.mod_group_id)
        dl = dl_map.get(corr.nexus_download_id)
        if not grp or not dl:
            session.delete(corr)
            existing.remove(corr)
            purged += 1
            continue
        score, _ = compute_name_score(grp.display_name, dl.mod_name)
        if score < 0.4:
            logger.info(
                "Purging stale correlation: '%s' -> '%s' (was %s/%.2f, now %.2f)",
                grp.display_name,
                dl.mod_name,
                corr.method,
                corr.score,
                score,
            )
            session.delete(corr)
            existing.remove(corr)
            purged += 1
    if purged:
        logger.info("Purged %d stale name-based correlations", purged)

    already_matched: set[int] = set()
    already_matched_nexus_ids: set[int] = set()
    for corr in existing:
        already_matched.add(corr.mod_group_id)
        dl = dl_map.get(corr.nexus_download_id)
        if dl:
            already_matched_nexus_ids.add(dl.nexus_mod_id)

    nexus_id_map: dict[int, NexusDownload] = {}
    for dl in downloads:
        if dl.nexus_mod_id:
            nexus_id_map.setdefault(dl.nexus_mod_id, dl)

    # Auto-correlate from installed mods (source of truth)
    installed_mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.nexus_mod_id.is_not(None),  # type: ignore[union-attr]
            InstalledMod.mod_group_id.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    for im in installed_mods:
        if im.mod_group_id in already_matched:
            continue
        dl = nexus_id_map.get(im.nexus_mod_id)  # type: ignore[arg-type]
        if not dl:
            continue
        corr = ModNexusCorrelation(
            mod_group_id=im.mod_group_id,  # type: ignore[arg-type]
            nexus_download_id=dl.id,  # type: ignore[arg-type]
            score=1.0,
            method="installed",
            reasoning=f"Auto-correlated from installed mod '{im.name}'",
            confirmed_by_user=True,
        )
        session.add(corr)
        already_matched.add(im.mod_group_id)  # type: ignore[arg-type]
        already_matched_nexus_ids.add(dl.nexus_mod_id)
        logger.info(
            "Auto-correlated group %d -> nexus %d from installed mod '%s'",
            im.mod_group_id,
            dl.nexus_mod_id,
            im.name,
        )

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
                dl_candidate = nexus_id_map[parsed.nexus_mod_id]
                if dl_candidate.nexus_mod_id not in already_matched_nexus_ids:
                    best_download = dl_candidate
                    best_score = 0.95
                    best_method = "filename_id"
                break

        # Slow path: fuzzy name matching
        if not best_download:
            for dl in downloads:
                if dl.nexus_mod_id in already_matched_nexus_ids:
                    continue
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
            already_matched_nexus_ids.add(best_download.nexus_mod_id)
            matched += 1

    # Deduplicate: if multiple groups point to the same nexus_mod_id, keep best
    _dedup_correlations(groups, session)

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
