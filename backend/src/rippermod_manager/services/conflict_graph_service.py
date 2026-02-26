import logging
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from sqlmodel import Session

from rippermod_manager.archive.handler import open_archive
from rippermod_manager.matching.filename_parser import parse_mod_filename
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


def build_conflict_graph(game: Game, session: Session) -> ConflictGraphResult:
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

    for archive_path in archives:
        parsed = parse_mod_filename(archive_path.name)
        # Skip archives that are already installed
        if _is_archive_installed(archive_path, ownership):
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

    # --- Build result, only including nodes that participate in conflicts ---
    conflict_node_ids: set[str] = set()
    edges: list[ConflictGraphEdge] = []
    for (src, tgt), files in edge_map.items():
        conflict_node_ids.add(src)
        conflict_node_ids.add(tgt)
        edges.append(
            ConflictGraphEdge(
                source=src,
                target=tgt,
                shared_files=sorted(files),
                weight=len(files),
            )
        )

    # Count conflicts per node
    conflict_counts: dict[str, int] = defaultdict(int)
    for edge in edges:
        conflict_counts[edge.source] += edge.weight
        conflict_counts[edge.target] += edge.weight

    nodes: list[ConflictGraphNode] = []
    for nid in sorted(conflict_node_ids):
        info = node_info[nid]
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
            )
        )

    return ConflictGraphResult(
        nodes=nodes,
        edges=edges,
        total_conflicts=sum(e.weight for e in edges),
    )


def _is_archive_installed(archive_path: Path, ownership: dict) -> bool:
    """Check if any installed mod was sourced from this archive."""
    archive_name = archive_path.name.lower()
    seen: set[int] = set()
    for mod in ownership.values():
        if mod.id not in seen:
            seen.add(mod.id)
            if mod.source_archive and mod.source_archive.lower() == archive_name:
                return True
    return False
