import re

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from rippermod_manager.matching.normalization import (
    SEPARATOR_RE,
    clean_display_name,
    split_camel,
    strip_ordering_prefix,
)
from rippermod_manager.models.mod import ModFile

VERSION_RE = re.compile(r"[_\-.]?v?\d+\.\d+(\.\d+)?[_\-.]?", re.IGNORECASE)


def normalize_name(name: str) -> str:
    name = strip_ordering_prefix(name)
    name = name.rsplit(".", 1)[0]
    name = VERSION_RE.sub(" ", name)
    name = split_camel(name)
    name = SEPARATOR_RE.sub(" ", name)
    return name.strip().lower()


def _extract_mod_folder(f: ModFile) -> str | None:
    """Return the immediate subfolder name under source_folder, or None for loose files."""
    fp = f.file_path.replace("\\", "/")
    sf = f.source_folder.replace("\\", "/").rstrip("/")
    if not fp.startswith(sf + "/"):
        return None
    remainder = fp[len(sf) + 1 :]
    if "/" not in remainder:
        return None
    folder = remainder.split("/", 1)[0]
    return folder if folder else None


def _cluster_loose_files(
    files: list[ModFile],
    eps: float,
) -> list[tuple[str, list[ModFile], float]]:
    """Cluster loose files using TF-IDF + DBSCAN."""
    if len(files) == 1:
        name = normalize_name(files[0].filename) or files[0].filename
        return [(name, files, 1.0)]

    doc_labels: list[str] = []
    file_map: list[ModFile] = []
    for f in files:
        parent_dir = f.source_folder.split("/")[-1] if "/" in f.source_folder else ""
        normalized = normalize_name(f.filename)
        tokens = f"{normalized} {parent_dir}".strip()
        doc_labels.append(tokens)
        file_map.append(f)

    if not doc_labels:
        return []

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
    tfidf_matrix = vectorizer.fit_transform(doc_labels)
    sim_matrix = cosine_similarity(tfidf_matrix)
    distance_matrix = 1.0 - sim_matrix
    np.fill_diagonal(distance_matrix, 0)
    distance_matrix = np.clip(distance_matrix, 0, None)

    clustering = DBSCAN(eps=eps, min_samples=1, metric="precomputed")
    labels = clustering.fit_predict(distance_matrix)

    clusters: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        clusters.setdefault(label, []).append(idx)

    results: list[tuple[str, list[ModFile], float]] = []
    for _label, indices in sorted(clusters.items()):
        cluster_files = [file_map[i] for i in indices]
        stems = [normalize_name(f.filename) for f in cluster_files]
        longest_stem = max(stems, key=len) if stems else ""
        group_name = longest_stem.title() if longest_stem else cluster_files[0].filename

        if len(indices) > 1:
            sub_sims = [
                sim_matrix[i][j] for idx_i, i in enumerate(indices) for j in indices[idx_i + 1 :]
            ]
            confidence = float(np.mean(sub_sims)) if sub_sims else 1.0
        else:
            confidence = 1.0

        results.append((group_name, cluster_files, round(confidence, 3)))

    return results


def _merge_same_name_groups(
    groups: list[tuple[str, list[ModFile], float]],
) -> list[tuple[str, list[ModFile], float]]:
    """Merge groups whose normalized names are identical (exact match only)."""
    buckets: dict[str, list[int]] = {}
    for idx, (name, _files, _conf) in enumerate(groups):
        key = normalize_name(name)
        buckets.setdefault(key, []).append(idx)

    merged: list[tuple[str, list[ModFile], float]] = []
    seen: set[int] = set()
    for idx, (name, files, conf) in enumerate(groups):
        if idx in seen:
            continue
        key = normalize_name(name)
        indices = buckets[key]
        if len(indices) == 1:
            merged.append((name, files, conf))
        else:
            # Merge all groups in this bucket
            combined_files: list[ModFile] = []
            best_name = name
            best_conf = conf
            for i in indices:
                seen.add(i)
                combined_files.extend(groups[i][1])
                # Pick the longest display name (most informative)
                if len(groups[i][0]) > len(best_name):
                    best_name = groups[i][0]
                best_conf = min(best_conf, groups[i][2])
            merged.append((best_name, combined_files, best_conf))

    return merged


def group_mod_files(
    files: list[ModFile], eps: float = 0.45
) -> list[tuple[str, list[ModFile], float]]:
    if not files:
        return []

    # Phase 1: Folder-based grouping (deterministic, O(n))
    folder_groups: dict[str, list[ModFile]] = {}
    loose_files: list[ModFile] = []
    for f in files:
        folder = _extract_mod_folder(f)
        if folder is not None:
            folder_groups.setdefault(folder, []).append(f)
        else:
            loose_files.append(f)

    results: list[tuple[str, list[ModFile], float]] = []
    for folder_name in sorted(folder_groups):
        display = clean_display_name(folder_name)
        results.append((display, folder_groups[folder_name], 1.0))

    # Phase 2: TF-IDF + DBSCAN for loose files only
    if loose_files:
        results.extend(_cluster_loose_files(loose_files, eps))

    # Phase 3: Merge groups with identical normalized names (cross-folder merge)
    results = _merge_same_name_groups(results)

    return results
