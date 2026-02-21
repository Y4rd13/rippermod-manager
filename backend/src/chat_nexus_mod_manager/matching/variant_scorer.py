"""File variant keyword scoring for Nexus Mods file matching.

When a mod has multiple file variants (e.g. Player vs NPC, 1K vs 4K textures),
this scorer helps pick the variant that best matches what the user already has installed.
"""

from typing import Any

from chat_nexus_mod_manager.models.install import InstalledMod

# Keyword pairs: (group_a, group_b) — if installed matches group_a, penalize group_b
VARIANT_KEYWORDS: list[tuple[set[str], set[str]]] = [
    ({"player"}, {"npc"}),
    ({"low"}, {"high"}),
    ({"lite", "light"}, {"full", "heavy"}),
    ({"1k"}, {"2k", "4k", "8k"}),
    ({"2k"}, {"1k", "4k", "8k"}),
    ({"4k"}, {"1k", "2k", "8k"}),
    ({"8k"}, {"1k", "2k", "4k"}),
    ({"performance"}, {"quality"}),
]

_ARCHIVED_CATEGORY_ID = 7


def _tokenize(text: str) -> set[str]:
    return set(text.lower().replace("-", " ").replace("_", " ").split())


def score_file_variant(
    candidate: dict[str, Any],
    installed_source_archive: str,
) -> int:
    """Score a candidate Nexus file against the installed variant.

    Returns score (higher = better match):
    - +100 for matching variant keyword
    - -100 for mismatching variant keyword
    - +5 for MAIN category (category_id == 1)
    - +25 for substring name match
    """
    score = 0
    installed_tokens = _tokenize(installed_source_archive)
    candidate_name = candidate.get("file_name", "") + " " + candidate.get("name", "")
    candidate_tokens = _tokenize(candidate_name)

    for group_a, group_b in VARIANT_KEYWORDS:
        installed_has_a = bool(installed_tokens & group_a)
        installed_has_b = bool(installed_tokens & group_b)
        candidate_has_a = bool(candidate_tokens & group_a)
        candidate_has_b = bool(candidate_tokens & group_b)

        if installed_has_a and candidate_has_a:
            score += 100
        if installed_has_a and candidate_has_b:
            score -= 100
        if installed_has_b and candidate_has_b:
            score += 100
        if installed_has_b and candidate_has_a:
            score -= 100

    if candidate.get("category_id") == 1:
        score += 5

    # Substring name match bonus (require >= 4 chars to avoid false positives)
    installed_name_lower = installed_source_archive.lower()
    cand_file_name = candidate.get("file_name", "").lower()
    cand_prefix = cand_file_name.split("-")[0] if cand_file_name else ""
    if len(cand_prefix) >= 4 and cand_prefix in installed_name_lower:
        score += 25

    return score


def pick_best_file(
    nexus_files: list[dict[str, Any]],
    installed_mod: InstalledMod,
) -> dict[str, Any] | None:
    """Select the best file for update, combining priority logic with variant scoring.

    1. Filter out archived files (category_id == 3)
    2. Run existing priority logic (timestamp/file_id match)
    3. Use variant scoring as tiebreaker among same-category candidates
    """
    if not nexus_files:
        return None

    # Filter out archived files
    active_files = [f for f in nexus_files if f.get("category_id") != _ARCHIVED_CATEGORY_ID]
    if not active_files:
        active_files = nexus_files

    # Priority 1: exact timestamp match -> return best variant in same category
    if installed_mod.upload_timestamp:
        matched_file = None
        for f in active_files:
            if f.get("uploaded_timestamp") == installed_mod.upload_timestamp:
                matched_file = f
                break

        if matched_file:
            category = matched_file.get("category_id")
            same_category = [f for f in active_files if f.get("category_id") == category]
            if len(same_category) > 1 and installed_mod.source_archive:
                same_category.sort(
                    key=lambda f: score_file_variant(f, installed_mod.source_archive),
                    reverse=True,
                )
                return same_category[0]
            if same_category:
                return max(same_category, key=lambda f: f.get("uploaded_timestamp", 0))
            return matched_file

    # Priority 2: file_id match
    if installed_mod.nexus_file_id:
        matched = None
        for f in active_files:
            if f.get("file_id") == installed_mod.nexus_file_id:
                matched = f
                break
        if matched:
            category = matched.get("category_id")
            same_category = [f for f in active_files if f.get("category_id") == category]
            if len(same_category) > 1 and installed_mod.source_archive:
                same_category.sort(
                    key=lambda f: score_file_variant(f, installed_mod.source_archive),
                    reverse=True,
                )
                return same_category[0]
            if same_category:
                return max(same_category, key=lambda f: f.get("uploaded_timestamp", 0))
            return matched

    # Priority 3: most recent MAIN file with variant scoring
    main_files = [f for f in active_files if f.get("category_id") == 1]
    if main_files:
        if len(main_files) > 1 and installed_mod.source_archive:
            main_files.sort(
                key=lambda f: score_file_variant(f, installed_mod.source_archive),
                reverse=True,
            )
            return main_files[0]
        return max(main_files, key=lambda f: f.get("uploaded_timestamp", 0))

    # Priority 4: most recent file with variant scoring tiebreaker
    if len(active_files) > 1 and installed_mod.source_archive:
        active_files.sort(
            key=lambda f: (
                score_file_variant(f, installed_mod.source_archive),
                f.get("uploaded_timestamp", 0),
            ),
            reverse=True,
        )
        return active_files[0]

    return max(active_files, key=lambda f: f.get("uploaded_timestamp", 0))
