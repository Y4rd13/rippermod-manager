"""Match endorsed/tracked mods to local files using Nexus CDN filenames.

Primary strategy: use exact ``NexusModFile.file_name`` values (the CDN
filenames users actually downloaded) to find archives in ``downloaded_mods/``.
Fallback: parse ``nexus_mod_id`` from archive filenames via regex.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from chat_nexus_mod_manager.archive.handler import open_archive
from chat_nexus_mod_manager.matching.correlator import compute_name_score
from chat_nexus_mod_manager.matching.filename_parser import parse_mod_filename
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.mod import ModFile, ModGroup
from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModFile, NexusModMeta
from chat_nexus_mod_manager.services.install_service import list_available_archives

logger = logging.getLogger(__name__)

# Nexus file category IDs
CAT_MAIN = 1
CAT_UPDATE = 2
CAT_OPTIONAL = 3
CAT_OLD_VERSION = 4
CAT_DELETED = 6
CAT_ARCHIVED = 7
_SKIP_CATEGORIES = {CAT_OLD_VERSION, CAT_DELETED, CAT_ARCHIVED}

# Category sort priority — lower = higher priority
_CAT_PRIORITY = {CAT_MAIN: 0, CAT_UPDATE: 1, CAT_OPTIONAL: 2}

_MIN_MATCH_RATIO = 0.5
_SIZE_MATCH_RATIO = 0.8


@dataclass
class FileListMatchResult:
    checked: int = 0
    matched: int = 0
    skipped_no_archive: int = 0
    details: list[dict[str, str]] = field(default_factory=list)


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/").lower()


def _build_local_file_indexes(
    session: Session,
) -> tuple[dict[str, ModFile], dict[str, list[ModFile]]]:
    """Build path and leaf-filename indexes over all grouped ModFiles."""
    all_mod_files = session.exec(
        select(ModFile).where(
            ModFile.mod_group_id.is_not(None)  # type: ignore[union-attr]
        )
    ).all()

    path_index: dict[str, ModFile] = {}
    leaf_index: dict[str, list[ModFile]] = defaultdict(list)
    for mf in all_mod_files:
        norm = _normalize_path(mf.file_path)
        path_index[norm] = mf
        leaf = norm.rsplit("/", 1)[-1]
        leaf_index[leaf].append(mf)
    return path_index, leaf_index


def _match_archive_to_local(
    archive_path: Path,
    path_index: dict[str, ModFile],
    leaf_index: dict[str, list[ModFile]],
    already_correlated_groups: set[int],
) -> tuple[int | None, float, float]:
    """Open an archive and compare its entries against local ModFiles.

    Returns ``(best_group_id, match_ratio, size_ratio)`` or ``(None, 0, 0)``
    if the archive doesn't match well enough.
    """
    try:
        with open_archive(archive_path) as archive:
            entries = archive.list_entries()
    except Exception:
        logger.warning("Could not open archive: %s", archive_path)
        return None, 0.0, 0.0

    file_entries = [e for e in entries if not e.is_dir and e.size > 0]
    if not file_entries:
        return None, 0.0, 0.0

    matched_files: list[tuple[object, ModFile]] = []
    for entry in file_entries:
        norm_entry = _normalize_path(entry.filename)
        mf = path_index.get(norm_entry)
        if not mf:
            leaf = norm_entry.rsplit("/", 1)[-1]
            candidates = leaf_index.get(leaf, [])
            if len(candidates) == 1:
                mf = candidates[0]
        if mf:
            matched_files.append((entry, mf))

    match_ratio = len(matched_files) / len(file_entries) if file_entries else 0.0
    if match_ratio < _MIN_MATCH_RATIO:
        return None, match_ratio, 0.0

    group_counts: dict[int, int] = defaultdict(int)
    for _, mf in matched_files:
        if mf.mod_group_id is not None:
            group_counts[mf.mod_group_id] += 1

    if not group_counts:
        return None, match_ratio, 0.0

    best_group_id = max(group_counts, key=group_counts.get)  # type: ignore[arg-type]
    if best_group_id in already_correlated_groups:
        return None, match_ratio, 0.0

    size_matches = 0
    size_compared = 0
    for entry, mf in matched_files:
        if entry.size > 0 and mf.file_size > 0:
            size_compared += 1
            if entry.size == mf.file_size:
                size_matches += 1

    size_ratio = size_matches / size_compared if size_compared > 0 else 0.0
    return best_group_id, match_ratio, size_ratio


def match_endorsed_to_local(
    game: Game,
    session: Session,
    on_progress: object = None,
) -> FileListMatchResult:
    """Match endorsed/tracked mods to local files via CDN filename lookup."""
    result = FileListMatchResult()

    downloads = session.exec(
        select(NexusDownload).where(
            NexusDownload.game_id == game.id,
            (NexusDownload.is_endorsed.is_(True)) | (NexusDownload.is_tracked.is_(True)),
        )
    ).all()
    if not downloads:
        return result

    # Skip downloads that already have a correlation
    corr_dl_ids = set(session.exec(select(ModNexusCorrelation.nexus_download_id)).all())
    uncorrelated = [dl for dl in downloads if dl.id not in corr_dl_ids]
    if not uncorrelated:
        return result

    # Build local archive index: {filename_lower: Path}
    archives = list_available_archives(game)
    local_archive_index: dict[str, Path] = {p.name.lower(): p for p in archives}

    # Build ModFile indexes for archive content matching
    path_index, leaf_index = _build_local_file_indexes(session)

    # Track already-correlated groups to avoid duplicates
    already_correlated_groups: set[int] = set(
        gid
        for gid in session.exec(select(ModNexusCorrelation.mod_group_id)).all()
        if gid is not None
    )

    # Collect NexusModFile rows per nexus_mod_id (only for our downloads)
    nexus_mod_ids = {dl.nexus_mod_id for dl in uncorrelated}
    all_nf = session.exec(
        select(NexusModFile).where(
            NexusModFile.nexus_mod_id.in_(nexus_mod_ids)  # type: ignore[union-attr]
        )
    ).all()
    # Track ALL mod IDs that have any NexusModFile data (before filtering)
    mods_with_nexus_files: set[int] = {nf.nexus_mod_id for nf in all_nf}
    nf_by_mod: dict[int, list[NexusModFile]] = defaultdict(list)
    for nf in all_nf:
        if nf.category_id not in _SKIP_CATEGORIES:
            nf_by_mod[nf.nexus_mod_id].append(nf)

    # Sort each mod's files by category priority (MAIN first)
    for mod_id in nf_by_mod:
        nf_by_mod[mod_id].sort(key=lambda f: _CAT_PRIORITY.get(f.category_id or 0, 99))

    # Track downloads that matched via CDN filename (skip in fallback)
    matched_dl_ids: set[int] = set()

    # --- Primary: CDN filename matching ---
    for dl in uncorrelated:
        nexus_files = nf_by_mod.get(dl.nexus_mod_id, [])
        if not nexus_files:
            continue

        result.checked += 1
        matched = False

        for nf in nexus_files:
            if not nf.file_name:
                continue
            local_path = local_archive_index.get(nf.file_name.lower())
            if not local_path:
                continue

            group_id, match_ratio, size_ratio = _match_archive_to_local(
                local_path,
                path_index,
                leaf_index,
                already_correlated_groups,
            )
            if group_id is None:
                continue

            sizes_match = size_ratio >= _SIZE_MATCH_RATIO
            if sizes_match and nf.version:
                dl.version = nf.version
            elif not sizes_match:
                dl.version = "0.0.0-unverified"

            corr = ModNexusCorrelation(
                mod_group_id=group_id,
                nexus_download_id=dl.id,  # type: ignore[arg-type]
                score=0.95,
                method="file_list",
                reasoning=(
                    f"CDN filename '{nf.file_name}' found locally, "
                    f"{match_ratio:.0%} content match, "
                    f"size match {size_ratio:.0%}"
                ),
            )
            session.add(corr)
            already_correlated_groups.add(group_id)
            matched_dl_ids.add(dl.id)  # type: ignore[arg-type]
            result.matched += 1
            result.details.append(
                {
                    "mod_name": dl.mod_name,
                    "archive": local_path.name,
                    "match_ratio": f"{match_ratio:.0%}",
                    "size_match": f"{size_ratio:.0%}",
                    "version_set": dl.version,
                    "method": "cdn_filename",
                }
            )
            matched = True
            break

        if not matched:
            result.skipped_no_archive += 1

    # --- Fallback: parse_mod_filename regex matching ---
    # Only for mods with NO NexusModFile data at all (not filtered-out ones)
    fallback_dls = [
        dl
        for dl in uncorrelated
        if dl.id not in matched_dl_ids and dl.nexus_mod_id not in mods_with_nexus_files
    ]
    if fallback_dls:
        archive_id_map: dict[int, list[Path]] = defaultdict(list)
        for archive_path in archives:
            parsed = parse_mod_filename(archive_path.name)
            if parsed.nexus_mod_id is not None:
                archive_id_map[parsed.nexus_mod_id].append(archive_path)

        for dl in fallback_dls:
            if dl.nexus_mod_id not in archive_id_map:
                continue

            result.checked += 1

            for archive_path in archive_id_map[dl.nexus_mod_id]:
                parsed = parse_mod_filename(archive_path.name)
                group_id, match_ratio, size_ratio = _match_archive_to_local(
                    archive_path,
                    path_index,
                    leaf_index,
                    already_correlated_groups,
                )
                if group_id is None:
                    continue

                sizes_match = size_ratio >= _SIZE_MATCH_RATIO
                if sizes_match and parsed.version:
                    dl.version = parsed.version
                elif not sizes_match:
                    dl.version = "0.0.0-unverified"

                corr = ModNexusCorrelation(
                    mod_group_id=group_id,
                    nexus_download_id=dl.id,  # type: ignore[arg-type]
                    score=0.92,
                    method="file_list",
                    reasoning=(
                        f"Fallback: archive '{archive_path.name}' "
                        f"matches {match_ratio:.0%} local files, "
                        f"size match {size_ratio:.0%}"
                    ),
                )
                session.add(corr)
                already_correlated_groups.add(group_id)
                result.matched += 1
                result.details.append(
                    {
                        "mod_name": dl.mod_name,
                        "archive": archive_path.name,
                        "match_ratio": f"{match_ratio:.0%}",
                        "size_match": f"{size_ratio:.0%}",
                        "version_set": dl.version,
                        "method": "fallback_filename_id",
                    }
                )
                break

    if result.matched > 0:
        session.commit()

    logger.info(
        "File list matching: checked=%d, matched=%d, skipped=%d",
        result.checked,
        result.matched,
        result.skipped_no_archive,
    )
    return result


_ENDORSED_NAME_THRESHOLD = 0.55
_ENDORSED_MIN_SCORE = 0.85


def match_endorsed_by_name(
    game: Game,
    session: Session,
) -> FileListMatchResult:
    """Match endorsed/tracked mods to local groups by name similarity.

    This catches mods where the user installed manually (no archive left) but
    the mod is in their endorsed/tracked list.  Runs after archive-based
    matching and before the general correlator.
    """
    result = FileListMatchResult()

    downloads = session.exec(
        select(NexusDownload).where(
            NexusDownload.game_id == game.id,
            (NexusDownload.is_endorsed.is_(True)) | (NexusDownload.is_tracked.is_(True)),
        )
    ).all()
    if not downloads:
        return result

    # Collect already-correlated download IDs and group IDs
    all_corr = session.exec(select(ModNexusCorrelation)).all()
    corr_dl_ids: set[int] = set()
    corr_group_ids: set[int] = set()
    corr_nexus_ids: set[int] = set()
    for c in all_corr:
        corr_dl_ids.add(c.nexus_download_id)
        if c.mod_group_id is not None:
            corr_group_ids.add(c.mod_group_id)

    # Also track which nexus_mod_ids are already correlated
    for dl in downloads:
        if dl.id in corr_dl_ids:
            corr_nexus_ids.add(dl.nexus_mod_id)

    uncorrelated_dls = [dl for dl in downloads if dl.id not in corr_dl_ids]
    if not uncorrelated_dls:
        return result

    # Get uncorrelated groups for this game
    all_groups = session.exec(select(ModGroup).where(ModGroup.game_id == game.id)).all()
    uncorrelated_groups = [g for g in all_groups if g.id not in corr_group_ids]
    if not uncorrelated_groups:
        return result

    # Fetch NexusModMeta names (often more accurate than NexusDownload.mod_name)
    meta_rows = session.exec(
        select(NexusModMeta).where(
            NexusModMeta.nexus_mod_id.in_(  # type: ignore[union-attr]
                [dl.nexus_mod_id for dl in uncorrelated_dls]
            )
        )
    ).all()
    meta_name_map: dict[int, str] = {m.nexus_mod_id: m.name for m in meta_rows}

    matched_group_ids: set[int] = set()
    matched_nexus_ids: set[int] = set()

    for dl in uncorrelated_dls:
        if dl.nexus_mod_id in matched_nexus_ids or dl.nexus_mod_id in corr_nexus_ids:
            continue

        result.checked += 1
        best_score = 0.0
        best_group: ModGroup | None = None

        dl_name = dl.mod_name
        meta_name = meta_name_map.get(dl.nexus_mod_id, "")

        for group in uncorrelated_groups:
            if group.id in matched_group_ids:
                continue

            score_dl, _ = compute_name_score(group.display_name, dl_name)
            score_meta = 0.0
            if meta_name:
                score_meta, _ = compute_name_score(group.display_name, meta_name)

            score = max(score_dl, score_meta)
            if score > best_score:
                best_score = score
                best_group = group

        if best_group and best_score >= _ENDORSED_NAME_THRESHOLD:
            boosted_score = max(best_score, _ENDORSED_MIN_SCORE)
            corr = ModNexusCorrelation(
                mod_group_id=best_group.id,  # type: ignore[arg-type]
                nexus_download_id=dl.id,  # type: ignore[arg-type]
                score=boosted_score,
                method="endorsed_name",
                reasoning=(
                    f"Endorsed mod '{dl_name}' matched to "
                    f"local group '{best_group.display_name}' "
                    f"(name similarity {best_score:.2f}, boosted to {boosted_score:.2f})"
                ),
            )
            session.add(corr)
            matched_group_ids.add(best_group.id)  # type: ignore[arg-type]
            matched_nexus_ids.add(dl.nexus_mod_id)
            result.matched += 1
            result.details.append(
                {
                    "mod_name": dl_name,
                    "local_group": best_group.display_name,
                    "raw_score": f"{best_score:.2f}",
                    "boosted_score": f"{boosted_score:.2f}",
                    "method": "endorsed_name",
                }
            )

    if result.matched > 0:
        session.commit()

    logger.info(
        "Endorsed name matching: checked=%d, matched=%d",
        result.checked,
        result.matched,
    )
    return result
