"""Who owns a destination path when several installed mods ship it (S4).

A destination is keyed case-insensitively with ``/`` separators; a REDmod
file is keyed by its ``mods/<name>`` junction root, because the junction, not
the file, is what lands in the game dir. Among the mods that own a key, the
one with the highest ``InstalledModFile.win_seq`` wins (ties: oldest
``installed_at``, then lowest id), and only an *enabled* winner is linked.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.paths import get_mods_dir
from rippermod_manager.services.vfs.primitives import verify_link

Owner = tuple[InstalledMod, InstalledModFile]


def path_key(relative_path: str, link_kind: str) -> str:
    """Return the ownership key of a file: lower-case, ``/``-separated."""
    rel = relative_path.replace("\\", "/").lower()
    if link_kind == "junction":
        parts = rel.split("/")
        if len(parts) >= 2 and parts[0] == "mods":
            return f"mods/{parts[1]}"
    return rel


def _ts(value: datetime) -> float:
    # SQLite hands datetimes back naive; they were written as UTC.
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).timestamp()


def _rank(owner: Owner) -> tuple[int, float, int]:
    mod, f = owner
    return (-f.win_seq, _ts(mod.installed_at), mod.id or 0)


def owners_by_key(session: Session, game_id: int) -> dict[str, list[Owner]]:
    """Every mod (enabled or not) that owns each key, best first.

    One entry per mod and key: a REDmod contributes many files to one junction
    key, and the one with the highest ``win_seq`` represents it.
    """
    rows = session.exec(
        select(InstalledMod, InstalledModFile)
        .where(InstalledModFile.installed_mod_id == InstalledMod.id)
        .where(InstalledMod.game_id == game_id)
    ).all()
    per_key: dict[str, dict[int, Owner]] = defaultdict(dict)
    for mod, f in rows:
        key = path_key(f.relative_path, f.link_kind)
        current = per_key[key].get(mod.id)  # type: ignore[arg-type]
        if current is None or f.win_seq > current[1].win_seq:
            per_key[key][mod.id] = (mod, f)  # type: ignore[index]
    return {key: sorted(owners.values(), key=_rank) for key, owners in per_key.items()}


def winner_map(session: Session, game_id: int) -> dict[str, Owner]:
    """The enabled owner that should be linked at each key."""
    result: dict[str, Owner] = {}
    for key, owners in owners_by_key(session, game_id).items():
        for mod, f in owners:
            if not mod.disabled:
                result[key] = (mod, f)
                break
    return result


def next_win_seq(session: Session, game_id: int) -> int:
    """A ``win_seq`` above every existing row of the game (at least 1)."""
    current = session.exec(
        select(func.max(InstalledModFile.win_seq))
        .join(InstalledMod, InstalledModFile.installed_mod_id == InstalledMod.id)  # type: ignore[arg-type]
        .where(InstalledMod.game_id == game_id)
    ).one()
    return max(int(current or 0) + 1, 1)


def _holds(game: Game, mod: InstalledMod, f: InstalledModFile) -> bool:
    """True when the game dir currently shows this mod's copy of the path."""
    install = Path(game.install_path)
    if f.link_kind == "junction":
        parts = f.relative_path.replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[0] == "mods":
            return (install / "mods" / parts[1]).is_dir()
    src = get_mods_dir(game) / mod.staging_dir / f.source_path.replace("\\", "/")
    return verify_link(src, install / f.relative_path.replace("\\", "/"))


def backfill_win_seq(game: Game, session: Session) -> int:
    """Give a win order to rows that predate ``win_seq`` (value 0).

    For each key with a 0 row, the owner whose link is in the game dir today
    ranks first (that is what the user sees in game), then by the existing
    order, then oldest ``installed_at`` (what ``plan_deploy`` linked first
    before S4). Owners get ``k..1``. Returns the number of rows updated, so a
    second run returns 0.
    """
    if game.id is None:
        return 0
    rows = session.exec(
        select(InstalledMod, InstalledModFile)
        .where(InstalledModFile.installed_mod_id == InstalledMod.id)
        .where(InstalledMod.game_id == game.id)
    ).all()
    files_by_key: dict[str, dict[int, list[InstalledModFile]]] = defaultdict(
        lambda: defaultdict(list)
    )
    mods: dict[int, InstalledMod] = {}
    for mod, f in rows:
        files_by_key[path_key(f.relative_path, f.link_kind)][mod.id].append(f)  # type: ignore[index]
        mods[mod.id] = mod  # type: ignore[index]

    updated = 0
    for per_mod in files_by_key.values():
        if not any(f.win_seq == 0 for files in per_mod.values() for f in files):
            continue

        def order(mod_id: int, per_mod=per_mod) -> tuple[bool, int, float, int]:
            mod = mods[mod_id]
            files = per_mod[mod_id]
            holder = any(_holds(game, mod, f) for f in files)
            best = max(f.win_seq for f in files)
            return (not holder, -best, _ts(mod.installed_at), mod_id)

        ranked = sorted(per_mod, key=order)
        for position, mod_id in enumerate(ranked):
            value = len(ranked) - position
            for f in per_mod[mod_id]:
                if f.win_seq != value:
                    f.win_seq = value
                    session.add(f)
                    updated += 1
    if updated:
        session.commit()
    return updated
