import json
import logging
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from sqlmodel import Session, select
from sqlmodel.sql.expression import Select

from rippermod_manager.archive.handler import open_archive
from rippermod_manager.matching.filename_parser import parse_mod_filename
from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.download import DownloadJob
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import ArchiveNexusLink, InstalledMod, InstalledModFile
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.schemas.conflicts import (
    ConflictCount,
    ConflictGraphEdge,
    ConflictGraphNode,
    ConflictGraphResult,
)
from rippermod_manager.services.archive_layout import (
    ArchiveLayout,
    apply_layout_transform,
    detect_layout,
    known_roots_for_game,
)
from rippermod_manager.services.install_service import (
    get_file_ownership_map,
    list_available_archives,
)
from rippermod_manager.services.paths import get_mods_dir
from rippermod_manager.services.presence_service import nexus_presence

logger = logging.getLogger(__name__)


# Last graph per game id, with the fingerprint it was built from. Every change that can
# alter the graph (install, uninstall, enable, disable, adopt, scan, link, confirm, reassign,
# rename, a new archive in staging, a reindex) changes the fingerprint, so no caller has to
# invalidate.
_GRAPH_CACHE: dict[int, tuple[tuple, ConflictGraphResult]] = {}


def _rows(session: Session, stmt: Select) -> tuple:
    return tuple(tuple(row) for row in session.exec(stmt).all())


def _fingerprint(game: Game, session: Session) -> tuple:
    """The rows the conflict graph of *game* is built from, plus the staging archives' stats.

    Rows, not counts or max(id): the tables have no AUTOINCREMENT, so SQLite reuses the freed
    highest id, and several of them are updated in place. Measured at 300 mods, 21k files,
    5k evidence rows and 100k index rows, the slowest query takes about 21 ms.
    """
    staged: list[tuple[str, int, int]] = []
    for path in list_available_archives(game):
        try:
            st = path.stat()
        except OSError:
            continue
        staged.append((path.name, st.st_size, st.st_mtime_ns))

    mods = _rows(
        session,
        select(
            InstalledMod.id,
            InstalledMod.name,
            InstalledMod.disabled,
            InstalledMod.nexus_mod_id,
            InstalledMod.source_archive,
        )
        .where(InstalledMod.game_id == game.id)
        .order_by(InstalledMod.id),  # type: ignore[arg-type]
    )
    files = _rows(
        session,
        select(InstalledModFile.installed_mod_id, InstalledModFile.relative_path)
        .join(InstalledMod, InstalledModFile.installed_mod_id == InstalledMod.id)  # type: ignore[arg-type]
        .where(InstalledMod.game_id == game.id)
        .order_by(InstalledModFile.id),  # type: ignore[arg-type]
    )
    correlations = _rows(
        session,
        select(
            ModNexusCorrelation.mod_group_id,
            ModNexusCorrelation.nexus_download_id,
            ModNexusCorrelation.score,
            ModNexusCorrelation.confirmed_by_user,
        )
        .join(ModGroup, ModNexusCorrelation.mod_group_id == ModGroup.id)  # type: ignore[arg-type]
        .where(ModGroup.game_id == game.id)
        .order_by(ModNexusCorrelation.id),  # type: ignore[arg-type]
    )
    links = _rows(
        session,
        select(ArchiveNexusLink.filename, ArchiveNexusLink.nexus_mod_id)
        .where(ArchiveNexusLink.game_id == game.id)
        .order_by(ArchiveNexusLink.id),  # type: ignore[arg-type]
    )
    completed_jobs = _rows(
        session,
        select(DownloadJob.file_name, DownloadJob.nexus_mod_id)
        .where(DownloadJob.game_id == game.id, DownloadJob.status == "completed")
        .order_by(DownloadJob.id),  # type: ignore[arg-type]
    )
    evidence = _rows(
        session,
        select(ConflictEvidence.key, ConflictEvidence.detail)
        .where(
            ConflictEvidence.game_id == game.id,
            ConflictEvidence.kind == ConflictKind.archive_resource,
        )
        .order_by(ConflictEvidence.id),  # type: ignore[arg-type]
    )
    indexed = _rows(
        session,
        select(ArchiveEntryIndex.archive_filename, ArchiveEntryIndex.installed_mod_id)
        .where(
            ArchiveEntryIndex.game_id == game.id,
            ArchiveEntryIndex.installed_mod_id.is_not(None),  # type: ignore[union-attr]
        )
        .distinct()
        .order_by(ArchiveEntryIndex.archive_filename, ArchiveEntryIndex.installed_mod_id),
    )
    return (
        str(get_mods_dir(game)),
        tuple(sorted(staged)),
        mods,
        files,
        correlations,
        links,
        completed_jobs,
        evidence,
        indexed,
    )


def _archive_nexus_ids(game: Game, session: Session, archives: list[Path]) -> dict[str, int]:
    """Nexus mod id per archive filename: from the name, else ArchiveNexusLink, else a job."""
    names = [p.name for p in archives]
    ids: dict[str, int] = {}
    for fn, mid in session.exec(
        select(ArchiveNexusLink.filename, ArchiveNexusLink.nexus_mod_id).where(
            ArchiveNexusLink.game_id == game.id,
            ArchiveNexusLink.filename.in_(names),  # type: ignore[attr-defined]
        )
    ).all():
        ids[fn] = mid
    for fn, mid in session.exec(
        select(DownloadJob.file_name, DownloadJob.nexus_mod_id).where(
            DownloadJob.game_id == game.id,
            DownloadJob.status == "completed",
            DownloadJob.file_name.in_(names),  # type: ignore[attr-defined]
        )
    ).all():
        ids.setdefault(fn, mid)
    for name in names:
        parsed_id = parse_mod_filename(name).nexus_mod_id
        if parsed_id is not None:
            ids[name] = parsed_id
    return ids


def build_conflict_graph(
    game: Game,
    session: Session,
    *,
    resource_hash: str | None = None,
) -> ConflictGraphResult:
    """Conflict graph of the mods on disk: managed mods plus one archive per unmanaged mod.

    Served from cache while the game's fingerprint is unchanged, except when filtered by
    ``resource_hash``.
    """
    if resource_hash is not None:
        return _build_graph(game, session, resource_hash)

    fingerprint = _fingerprint(game, session)
    cached = _GRAPH_CACHE.get(game.id)  # type: ignore[arg-type]
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    result = _build_graph(game, session, None)
    _GRAPH_CACHE[game.id] = (fingerprint, result)  # type: ignore[index]
    return result


def conflict_count(game: Game, session: Session) -> ConflictCount:
    """Mods in some conflict edge (a dismissed managed mod excluded) and the files they share."""
    graph = build_conflict_graph(game, session)
    dismissed = {
        f"installed:{mod_id}"
        for mod_id in session.exec(
            select(InstalledMod.id).where(
                InstalledMod.game_id == game.id,
                InstalledMod.conflict_dismissed == True,  # noqa: E712
            )
        ).all()
    }
    involved = {e.source for e in graph.edges} | {e.target for e in graph.edges}
    return ConflictCount(
        mods_with_conflicts=len(involved - dismissed),
        file_conflicts=sum(e.weight for e in graph.edges),
    )


def _build_graph(game: Game, session: Session, resource_hash: str | None) -> ConflictGraphResult:
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

    # --- Uninstalled archives: one per unmanaged Nexus mod on disk, the newest ---
    archives = list_available_archives(game)
    known_roots = known_roots_for_game(game.domain_name)
    presence = nexus_presence(game, session)
    archive_ids = _archive_nexus_ids(game, session, archives)

    # Pre-compute installed archive names for O(1) lookup
    installed_archive_names: set[str] = set()
    seen_for_names: set[int] = set()
    for mod in ownership.values():
        if mod.id not in seen_for_names:
            seen_for_names.add(mod.id)
            if mod.source_archive:
                installed_archive_names.add(mod.source_archive.lower())

    newest: dict[int, tuple[int, Path]] = {}
    for archive_path in archives:
        if archive_path.name.lower() in installed_archive_names:
            continue
        nexus_id = archive_ids.get(archive_path.name)
        if (
            nexus_id is None
            or nexus_id in presence.managed_ids
            or not presence.is_on_disk(nexus_id)
        ):
            continue
        try:
            mtime = archive_path.stat().st_mtime_ns
        except OSError:
            continue
        if nexus_id not in newest or mtime > newest[nexus_id][0]:
            newest[nexus_id] = (mtime, archive_path)

    for nexus_id, (_mtime, archive_path) in sorted(newest.items()):
        parsed = parse_mod_filename(archive_path.name)
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
            normalised = apply_layout_transform(entry.filename, layout)
            if normalised is None:
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
                "nexus_mod_id": nexus_id,
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

    for ev in session.exec(ev_query).yield_per(500):
        try:
            detail = json.loads(ev.detail)
        except (json.JSONDecodeError, TypeError):
            continue
        winner = detail.get("winner_archive")
        if not winner:
            continue
        sha1s: dict[str, str] = detail.get("sha1s", {})
        winner_sha1 = sha1s.get(winner, "")
        winner_node = game_archive_to_node.get(winner)
        if not winner_node:
            continue
        for loser in detail.get("loser_archives", []):
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
        src_nexus = node_info.get(src, {}).get("nexus_mod_id")
        if src_nexus is not None and src_nexus == node_info.get(tgt, {}).get("nexus_mod_id"):
            continue  # two files of the same Nexus mod do not conflict with each other
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
