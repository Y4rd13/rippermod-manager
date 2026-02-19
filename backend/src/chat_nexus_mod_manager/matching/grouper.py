import re

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from chat_nexus_mod_manager.models.mod import ModFile

VERSION_RE = re.compile(r"[_\-.]?v?\d+\.\d+(\.\d+)?[_\-.]?", re.IGNORECASE)
SEPARATOR_RE = re.compile(r"[_\-.\s]+")


def normalize_name(name: str) -> str:
    name = name.rsplit(".", 1)[0]
    name = VERSION_RE.sub(" ", name)
    name = SEPARATOR_RE.sub(" ", name)
    return name.strip().lower()


def group_mod_files(
    files: list[ModFile], eps: float = 0.45
) -> list[tuple[str, list[ModFile], float]]:
    if not files:
        return []

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
