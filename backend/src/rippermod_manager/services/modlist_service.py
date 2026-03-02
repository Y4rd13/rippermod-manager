"""Modlist.txt generation and load-order preference management.

The RED engine (Cyberpunk 2077) loads ``.archive`` files from ``archive/pc/mod/``
in ASCII filename order by default.  When a ``modlist.txt`` file is present in that
directory, the engine uses the explicit order from the file instead.

This module manages user preferences ("prefer mod A over mod B") and translates
them into a ``modlist.txt`` that controls which mod's resources take priority
without renaming any files.
"""

from __future__ import annotations

import heapq
import logging
from collections import defaultdict
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.models.load_order import LoadOrderPreference
from rippermod_manager.schemas.load_order import (
    ModlistGroupEntry,
    ModlistViewResult,
    PreferenceOut,
)

logger = logging.getLogger(__name__)

_ARCHIVE_DIR = "archive/pc/mod"


def _scan_archive_files(game: Game) -> list[str]:
    """Enumerate all ``.archive`` files on disk in ``archive/pc/mod/``."""
    mod_dir = Path(game.install_path) / _ARCHIVE_DIR
    if not mod_dir.is_dir():
        return []
    return sorted(
        f.name for f in mod_dir.iterdir() if f.is_file() and f.suffix.lower() == ".archive"
    )


def _build_file_to_mod_map(session: Session, game_id: int) -> dict[str, int | None]:
    """Map archive filenames (lowercased) to their owning ``installed_mod_id``.

    Returns ``None`` for unmanaged archives (not tracked in the DB).
    """
    rows = session.exec(
        select(InstalledModFile.relative_path, InstalledModFile.installed_mod_id)
        .join(InstalledMod)
        .where(
            InstalledMod.game_id == game_id,
            InstalledMod.disabled == False,  # noqa: E712
        )
    ).all()

    file_map: dict[str, int | None] = {}
    for rel_path, mod_id in rows:
        normalised = rel_path.replace("\\", "/")
        lower = normalised.lower()
        if lower.startswith(_ARCHIVE_DIR.lower() + "/") and lower.endswith(".archive"):
            filename = normalised.rsplit("/", 1)[-1].lower()
            file_map[filename] = mod_id
    return file_map


def _compute_ordered_groups(
    game: Game, session: Session
) -> tuple[list[tuple[int | str, list[str]]], list[LoadOrderPreference]]:
    """Compute ordered groups of archives respecting user preferences.

    Returns ``(ordered_groups, preferences)`` where each group is
    ``(group_key, [filenames])``.  ``group_key`` is a mod ID (int) for managed
    mods or a string like ``"unmanaged_-1"`` for unmanaged archives.

    Algorithm:
    1. Scan disk for ``.archive`` files
    2. Map each to its owning mod (or ``None`` for unmanaged)
    3. Group archives by mod; each unmanaged archive is its own group
    4. Default order: groups sorted by their lowest filename (ASCII, case-insensitive)
    5. Apply ``LoadOrderPreference`` constraints via topological sort (Kahn's with min-heap)
    """
    disk_files = _scan_archive_files(game)
    if not disk_files:
        return [], []

    file_mod_map = _build_file_to_mod_map(session, game.id)  # type: ignore[arg-type]

    # Group archives by mod_id.  Unmanaged archives get a unique negative key.
    groups: dict[int | str, list[str]] = defaultdict(list)
    unmanaged_counter = 0
    for filename in disk_files:
        mod_id = file_mod_map.get(filename.lower())
        if mod_id is not None:
            groups[mod_id].append(filename)
        else:
            unmanaged_counter -= 1
            groups[f"unmanaged_{unmanaged_counter}"] = [filename]

    # Sort archives within each group by filename (case-insensitive)
    for key in groups:
        groups[key].sort(key=lambda fn: fn.lower())

    # Default sort key for each group: lowest filename (case-insensitive)
    group_sort_key: dict[int | str, str] = {}
    for key, files in groups.items():
        group_sort_key[key] = files[0].lower()

    # Assign integer indices for topological sort — ordered by default sort key
    sorted_group_keys = sorted(groups.keys(), key=lambda k: group_sort_key[k])
    key_to_idx: dict[int | str, int] = {k: i for i, k in enumerate(sorted_group_keys)}
    n = len(sorted_group_keys)

    # Build adjacency for preferences (winner must come before loser)
    adj: dict[int, list[int]] = defaultdict(list)
    in_degree: dict[int, int] = {i: 0 for i in range(n)}

    preferences = list(
        session.exec(
            select(LoadOrderPreference).where(LoadOrderPreference.game_id == game.id)
        ).all()
    )

    for pref in preferences:
        winner_idx = key_to_idx.get(pref.winner_mod_id)
        loser_idx = key_to_idx.get(pref.loser_mod_id)
        if winner_idx is None or loser_idx is None:
            continue
        if winner_idx == loser_idx:
            continue
        adj[winner_idx].append(loser_idx)
        in_degree[loser_idx] += 1

    # Kahn's algorithm with min-heap (stable: preserves default ASCII order)
    heap = [i for i in range(n) if in_degree[i] == 0]
    heapq.heapify(heap)

    topo_order: list[int] = []
    while heap:
        node = heapq.heappop(heap)
        topo_order.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                heapq.heappush(heap, neighbor)

    if len(topo_order) < n:
        remaining = [i for i in range(n) if i not in set(topo_order)]
        logger.warning(
            "Cycle detected in load order preferences; %d group(s) could not be sorted. "
            "Appending in default order.",
            len(remaining),
        )
        topo_order.extend(sorted(remaining))

    ordered = [(sorted_group_keys[idx], groups[sorted_group_keys[idx]]) for idx in topo_order]
    return ordered, preferences


def generate_modlist(game: Game, session: Session) -> list[str]:
    """Generate an ordered list of archive filenames respecting user preferences.

    1. Scan disk for ``.archive`` files
    2. Map each to its owning mod (or ``None`` for unmanaged)
    3. Group archives by mod; each unmanaged archive is its own group
    4. Default order: groups sorted by their lowest filename (ASCII, case-insensitive)
    5. Apply ``LoadOrderPreference`` constraints via topological sort (Kahn's with min-heap)
    6. Emit filenames in group order, archives sorted within each group
    """
    ordered_groups, _ = _compute_ordered_groups(game, session)
    return [fn for _, files in ordered_groups for fn in files]


def write_modlist(game: Game, session: Session) -> int:
    """Generate and write ``modlist.txt`` to the game's archive/pc/mod/ directory.

    Returns the number of entries written.
    """
    ordered = generate_modlist(game, session)
    mod_dir = Path(game.install_path) / _ARCHIVE_DIR
    mod_dir.mkdir(parents=True, exist_ok=True)
    modlist_path = mod_dir / "modlist.txt"

    if not ordered:
        if modlist_path.exists():
            modlist_path.unlink()
        return 0

    modlist_path.write_text("\n".join(ordered) + "\n", encoding="utf-8")
    logger.info("Wrote modlist.txt with %d entries to %s", len(ordered), modlist_path)
    return len(ordered)


def add_preferences(
    game_id: int,
    winner_mod_id: int,
    loser_mod_ids: list[int],
    game: Game,
    session: Session,
) -> int:
    """Add load-order preferences (winner before each loser).

    Handles duplicates and reversal of existing preferences.
    Returns the number of new preferences added.
    """
    added = 0
    for loser_mod_id in loser_mod_ids:
        if loser_mod_id == winner_mod_id:
            continue

        # Check for existing identical preference
        existing = session.exec(
            select(LoadOrderPreference).where(
                LoadOrderPreference.game_id == game_id,
                LoadOrderPreference.winner_mod_id == winner_mod_id,
                LoadOrderPreference.loser_mod_id == loser_mod_id,
            )
        ).first()
        if existing:
            continue

        # Remove reverse preference if it exists
        reverse = session.exec(
            select(LoadOrderPreference).where(
                LoadOrderPreference.game_id == game_id,
                LoadOrderPreference.winner_mod_id == loser_mod_id,
                LoadOrderPreference.loser_mod_id == winner_mod_id,
            )
        ).first()
        if reverse:
            session.delete(reverse)

        session.add(
            LoadOrderPreference(
                game_id=game_id,
                winner_mod_id=winner_mod_id,
                loser_mod_id=loser_mod_id,
            )
        )
        added += 1

    session.commit()
    entries = write_modlist(game, session)
    logger.info(
        "Added %d preference(s) for game %d, modlist.txt has %d entries",
        added,
        game_id,
        entries,
    )
    return added


def remove_preference(
    game_id: int,
    winner_mod_id: int,
    loser_mod_id: int,
    game: Game,
    session: Session,
) -> bool:
    """Remove a single load-order preference and regenerate modlist.txt."""
    pref = session.exec(
        select(LoadOrderPreference).where(
            LoadOrderPreference.game_id == game_id,
            LoadOrderPreference.winner_mod_id == winner_mod_id,
            LoadOrderPreference.loser_mod_id == loser_mod_id,
        )
    ).first()
    if not pref:
        return False
    session.delete(pref)
    session.commit()
    write_modlist(game, session)
    return True


def get_preferences(game_id: int, session: Session) -> list[LoadOrderPreference]:
    """Return all load-order preferences for a game."""
    return list(
        session.exec(
            select(LoadOrderPreference).where(LoadOrderPreference.game_id == game_id)
        ).all()
    )


def get_modlist_view(game: Game, session: Session) -> ModlistViewResult:
    """Build the modlist view showing ordered groups, preferences, and status."""
    ordered_groups, preferences = _compute_ordered_groups(game, session)

    # Build mod name lookup
    mod_ids = [key for key, _ in ordered_groups if isinstance(key, int)]
    mod_names: dict[int, str] = {}
    if mod_ids:
        mods = session.exec(select(InstalledMod).where(InstalledMod.id.in_(mod_ids))).all()  # type: ignore[union-attr]
        mod_names = {m.id: m.name for m in mods if m.id is not None}

    # Build set of mod IDs that appear in any preference
    pref_mod_ids: set[int] = set()
    for pref in preferences:
        pref_mod_ids.add(pref.winner_mod_id)
        pref_mod_ids.add(pref.loser_mod_id)

    # Build group entries
    group_entries: list[ModlistGroupEntry] = []
    total_archives = 0
    for position, (key, files) in enumerate(ordered_groups, start=1):
        is_unmanaged = isinstance(key, str)
        mod_id = None if is_unmanaged else key
        mod_name = "Unmanaged" if is_unmanaged else mod_names.get(key, f"Mod #{key}")  # type: ignore[arg-type]
        total_archives += len(files)
        group_entries.append(
            ModlistGroupEntry(
                position=position,
                mod_id=mod_id,
                mod_name=mod_name,
                archive_filenames=files,
                archive_count=len(files),
                is_unmanaged=is_unmanaged,
                has_user_preference=mod_id is not None and mod_id in pref_mod_ids,
            )
        )

    # Build preference entries with resolved names
    pref_entries: list[PreferenceOut] = []
    for pref in preferences:
        pref_entries.append(
            PreferenceOut(
                id=pref.id,  # type: ignore[arg-type]
                winner_mod_id=pref.winner_mod_id,
                winner_mod_name=mod_names.get(pref.winner_mod_id, f"Mod #{pref.winner_mod_id}"),
                loser_mod_id=pref.loser_mod_id,
                loser_mod_name=mod_names.get(pref.loser_mod_id, f"Mod #{pref.loser_mod_id}"),
            )
        )

    modlist_path = Path(game.install_path) / _ARCHIVE_DIR / "modlist.txt"
    return ModlistViewResult(
        game_name=game.name,
        groups=group_entries,
        preferences=pref_entries,
        total_archives=total_archives,
        total_groups=len(group_entries),
        total_preferences=len(preferences),
        modlist_active=modlist_path.is_file(),
        modlist_path=str(modlist_path),
    )


def remove_all_preferences(game_id: int, game: Game, session: Session) -> int:
    """Delete all load-order preferences for a game and regenerate modlist.txt.

    Returns the number of preferences removed.
    """
    prefs = session.exec(
        select(LoadOrderPreference).where(LoadOrderPreference.game_id == game_id)
    ).all()
    count = len(prefs)
    for pref in prefs:
        session.delete(pref)
    session.commit()
    write_modlist(game, session)
    logger.info("Removed all %d preferences for game %d", count, game_id)
    return count
