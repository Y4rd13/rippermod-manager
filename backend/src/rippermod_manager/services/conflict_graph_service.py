import json
import logging
from collections import defaultdict
from itertools import combinations

from sqlmodel import Session, select

from rippermod_manager.archive.handler import open_archive
from rippermod_manager.matching.filename_parser import parse_mod_filename
from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind
from rippermod_manager.models.game import Game
from rippermod_manager.schemas.conflicts import (
    ConflictGraphEdge,
    ConflictGraphNode,
    ConflictGraphResult,
)
from rippermod_manager.services.archive_layout import (
    ArchiveLayout,
    detect_layout,
    known_roots_for_game,
)
from rippermod_manager.services.install_service import (
    get_file_ownership_map,
    list_available_archives,
)

logger = logging.getLogger(__name__)


def build_conflict_graph(
    game: Game,
    session: Session,
    *,
    resource_hash: str | None = None,
) -> ConflictGraphResult:
    """Build a conflict graph across all installed mods and uninstalled archives."""
    ownership = get_file_ownership_map(session, game.id)  # type: ignore[arg-type]

    # Collect node metadata: {node_id: {label, source_type, file_count, ...}}
    node_info: dict[str, dict] = {}
    # Reverse index: {normalised_path: [node_ids]}
    path_to_nodes: dict[str, list[str]] = defaultdict(list)

    # --- Installed mods ---
    mod_files: dict[str, set[str]] = defaultdict(set)
    for path, mod in ownership.items():
        node_id = f"installed:{mod.id}"
        mod_files[node_id].add(path)
        path_to_nodes[path].append(node_id)

    seen_mod_ids: set[int] = set()
    for mod in ownership.values():
        if mod.id in seen_mod_ids:
            continue
        seen_mod_ids.add(mod.id)  # type: ignore[arg-type]
        node_id = f"installed:{mod.id}"
        node_info[node_id] = {
            "label": mod.name,
            "source_type": "installed",
            "file_count": len(mod_files[node_id]),
            "disabled": mod.disabled,
            "nexus_mod_id": mod.nexus_mod_id,
            "picture_url": None,
        }

    # --- Uninstalled archives ---
    archives = list_available_archives(game)
    known_roots = known_roots_for_game(game.domain_name)

    # Pre-compute installed archive names for O(1) lookup
    installed_archive_names: set[str] = set()
    seen_for_names: set[int] = set()
    for mod in ownership.values():
        if mod.id not in seen_for_names:
            seen_for_names.add(mod.id)
            if mod.source_archive:
                installed_archive_names.add(mod.source_archive.lower())

    for archive_path in archives:
        parsed = parse_mod_filename(archive_path.name)
        if archive_path.name.lower() in installed_archive_names:
            continue

        try:
            with open_archive(archive_path) as archive:
                entries = archive.list_entries()
        except Exception:
            logger.warning("Could not open archive %s, skipping", archive_path.name)
            continue

        layout = detect_layout(entries, known_roots)
        if layout.layout == ArchiveLayout.FOMOD:
            continue

        node_id = f"archive:{archive_path.name}"
        file_paths: set[str] = set()

        for entry in entries:
            if entry.is_dir:
                continue
            normalised = entry.filename.replace("\\", "/")
            if layout.strip_prefix:
                prefix = layout.strip_prefix + "/"
                if normalised.startswith(prefix):
                    normalised = normalised[len(prefix) :]
                else:
                    continue
            normalised = normalised.lower()
            file_paths.add(normalised)
            path_to_nodes[normalised].append(node_id)

        if file_paths:
            node_info[node_id] = {
                "label": parsed.name,
                "source_type": "archive",
                "file_count": len(file_paths),
                "disabled": False,
                "nexus_mod_id": parsed.nexus_mod_id,
                "picture_url": None,
            }

    # --- Build edges from shared paths ---
    edge_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path, nodes in path_to_nodes.items():
        unique_nodes = sorted(set(nodes))
        if len(unique_nodes) < 2:
            continue
        for a, b in combinations(unique_nodes, 2):
            key = (a, b) if a < b else (b, a)
            edge_map[key].append(path)

    # --- Aggregate resource-level conflicts from ConflictEvidence ---
    # ConflictEvidence uses game .archive filenames (e.g. "CyberAds.archive"),
    # NOT download archive names (e.g. "Cyber Ads-26975-1-5-1.zip").
    # Use ArchiveEntryIndex to map .archive filename → installed_mod_id → node_id.
    game_archive_to_node: dict[str, str] = {}
    index_rows = session.exec(
        select(
            ArchiveEntryIndex.archive_filename,
            ArchiveEntryIndex.installed_mod_id,
        )
        .where(
            ArchiveEntryIndex.game_id == game.id,  # type: ignore[arg-type]
            ArchiveEntryIndex.installed_mod_id.is_not(None),  # type: ignore[union-attr]
        )
        .distinct()
    ).all()
    for arch_filename, mod_id in index_rows:
        nid = f"installed:{mod_id}"
        if nid in node_info:
            game_archive_to_node[arch_filename] = nid

    resource_edge_data: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"resource_conflicts": 0, "identical_resource_count": 0, "real_resource_count": 0}
    )

    ev_query = select(ConflictEvidence).where(
        ConflictEvidence.game_id == game.id,  # type: ignore[arg-type]
        ConflictEvidence.kind == ConflictKind.archive_resource,
    )
    if resource_hash:
        ev_query = ev_query.where(ConflictEvidence.key == resource_hash)
    resource_evidences = session.exec(ev_query).all()

    for ev in resource_evidences:
        detail = json.loads(ev.detail)
        winner = detail["winner_archive"]
        sha1s: dict[str, str] = detail.get("sha1s", {})
        winner_sha1 = sha1s.get(winner, "")
        winner_node = game_archive_to_node.get(winner)
        if not winner_node:
            continue
        for loser in detail["loser_archives"]:
            loser_node = game_archive_to_node.get(loser)
            if not loser_node or loser_node == winner_node:
                continue
            key = (
                (winner_node, loser_node) if winner_node < loser_node else (loser_node, winner_node)
            )
            rd = resource_edge_data[key]
            rd["resource_conflicts"] += 1
            loser_sha1 = sha1s.get(loser, "")
            if winner_sha1 and loser_sha1:
                if winner_sha1 == loser_sha1:
                    rd["identical_resource_count"] += 1
                else:
                    rd["real_resource_count"] += 1

    # --- Build result, only including nodes that participate in conflicts ---
    conflict_node_ids: set[str] = set()
    edges: list[ConflictGraphEdge] = []

    # Merge file edges with resource data
    all_edge_keys = set(edge_map.keys()) | set(resource_edge_data.keys())
    for key in all_edge_keys:
        src, tgt = key
        files = edge_map.get(key, [])
        rd = resource_edge_data.get(key, {})
        conflict_node_ids.add(src)
        conflict_node_ids.add(tgt)
        sorted_files = sorted(files)
        edges.append(
            ConflictGraphEdge(
                source=src,
                target=tgt,
                shared_files=sorted_files[:200],
                weight=len(files),
                resource_conflicts=rd.get("resource_conflicts", 0),
                identical_resource_count=rd.get("identical_resource_count", 0),
                real_resource_count=rd.get("real_resource_count", 0),
            )
        )

    # Count conflicts per node (file + resource)
    conflict_counts: dict[str, int] = defaultdict(int)
    resource_node_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "resource_conflict_count": 0,
            "real_resource_count": 0,
            "identical_resource_count": 0,
        }
    )
    for edge in edges:
        conflict_counts[edge.source] += edge.weight
        conflict_counts[edge.target] += edge.weight
        for nid in (edge.source, edge.target):
            rc = resource_node_counts[nid]
            rc["resource_conflict_count"] += edge.resource_conflicts
            rc["real_resource_count"] += edge.real_resource_count
            rc["identical_resource_count"] += edge.identical_resource_count

    nodes: list[ConflictGraphNode] = []
    for nid in sorted(conflict_node_ids):
        info = node_info.get(nid)
        if not info:
            continue
        rc = resource_node_counts.get(nid, {})
        nodes.append(
            ConflictGraphNode(
                id=nid,
                label=info["label"],
                source_type=info["source_type"],
                file_count=info["file_count"],
                conflict_count=conflict_counts[nid],
                disabled=info["disabled"],
                nexus_mod_id=info["nexus_mod_id"],
                picture_url=info["picture_url"],
                resource_conflict_count=rc.get("resource_conflict_count", 0),
                real_resource_count=rc.get("real_resource_count", 0),
                identical_resource_count=rc.get("identical_resource_count", 0),
            )
        )

    return ConflictGraphResult(
        nodes=nodes,
        edges=edges,
        total_conflicts=sum(e.weight for e in edges),
    )
