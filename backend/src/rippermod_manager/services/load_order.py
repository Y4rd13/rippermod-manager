"""Archive load-order computation and conflict resolution for RED engine games.

The RED engine (Cyberpunk 2077) loads ``.archive`` files from ``archive/pc/mod/``
in ASCII filename order (case-insensitive).  When two archives contain the same
internal resource, the **first** loaded archive wins.  This module computes the
load order, detects file-path level conflicts, and provides a "prefer mod"
action that renames archives to control which mod wins.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.schemas.load_order import (
    ConflictEvidence,
    LoadOrderEntry,
    LoadOrderResult,
    PreferModResult,
    RenameAction,
)

logger = logging.getLogger(__name__)

_PREFIX_RE = re.compile(r"^z+_", re.IGNORECASE)
_ARCHIVE_DIR = "archive/pc/mod/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_load_order_prefix(filename: str) -> str:
    """Remove any leading ``z+_`` prefix from a filename."""
    return _PREFIX_RE.sub("", filename)


def _compute_prefix(loser_min_filename: str) -> str:
    """Determine the minimal ``zz_`` / ``zzz_`` prefix that sorts after *loser_min_filename*.

    If the loser already starts with ``zz_``, we add one more ``z`` to guarantee
    the demoted archive sorts later.
    """
    stripped = loser_min_filename.lower()
    m = _PREFIX_RE.match(stripped)
    if m:
        existing_zs = len(m.group(0)) - 1  # minus the underscore
        return "z" * (existing_zs + 1) + "_"
    return "zz_"


def _get_mod_archive_files(mod: InstalledMod) -> list[InstalledModFile]:
    """Return the mod's ``.archive`` files under ``archive/pc/mod/``."""
    _ = mod.files  # force lazy-load
    return [
        f
        for f in mod.files
        if f.relative_path.replace("\\", "/").lower().startswith(_ARCHIVE_DIR)
        and f.relative_path.lower().endswith(".archive")
    ]


def _rollback_renames(
    completed: list[tuple[Path, Path]],
) -> bool:
    """Reverse completed renames.  Returns ``True`` if all rollbacks succeeded."""
    ok = True
    for new_path, old_path in reversed(completed):
        try:
            new_path.rename(old_path)
        except OSError:
            logger.error("Rollback failed: could not rename %s -> %s", new_path, old_path)
            ok = False
    return ok


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def get_archive_load_order(game: Game, session: Session) -> LoadOrderResult:
    """Compute the full archive load order and detect file-path conflicts."""
    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.disabled == False,  # noqa: E712
        )
    ).all()

    entries: list[LoadOrderEntry] = []
    # Map normalised relative_path -> list of (archive_filename, mod)
    path_owners: dict[str, list[tuple[str, InstalledMod]]] = {}

    for mod in mods:
        for f in _get_mod_archive_files(mod):
            rel = f.relative_path.replace("\\", "/")
            filename = rel.rsplit("/", 1)[-1]
            entries.append(
                LoadOrderEntry(
                    position=0,  # filled after sort
                    archive_filename=filename,
                    relative_path=rel,
                    owning_mod_id=mod.id,  # type: ignore[arg-type]
                    owning_mod_name=mod.name,
                    disabled=mod.disabled,
                )
            )
            norm = rel.lower()
            path_owners.setdefault(norm, []).append((filename, mod))

    # Sort by filename (case-insensitive ASCII order) — this is the RED engine order
    entries.sort(key=lambda e: e.archive_filename.lower())
    for i, entry in enumerate(entries):
        entry.position = i

    # Detect conflicts: same normalised relative_path claimed by multiple mods
    conflicts: list[ConflictEvidence] = []
    for norm_path, owners in path_owners.items():
        if len(owners) < 2:
            continue
        # Sort owners by archive filename to determine winner (first loaded wins).
        # NOTE: when two mods share the exact same filename, the winner is
        # ambiguous (one physically overwrites the other during install).
        sorted_owners = sorted(owners, key=lambda o: o[0].lower())
        winner_filename, winner_mod = sorted_owners[0]
        for loser_filename, loser_mod in sorted_owners[1:]:
            if loser_mod.id == winner_mod.id:
                continue
            conflicts.append(
                ConflictEvidence(
                    file_path=norm_path,
                    winner_mod_id=winner_mod.id,  # type: ignore[arg-type]
                    winner_mod_name=winner_mod.name,
                    winner_archive=winner_filename,
                    loser_mod_id=loser_mod.id,  # type: ignore[arg-type]
                    loser_mod_name=loser_mod.name,
                    loser_archive=loser_filename,
                    reasoning=(
                        f"'{winner_filename}' sorts before '{loser_filename}' "
                        f"(case-insensitive ASCII); first loaded wins"
                    ),
                )
            )

    return LoadOrderResult(
        game_name=game.name,
        total_archives=len(entries),
        load_order=entries,
        conflicts=conflicts,
    )


def generate_prefer_renames(
    winner_mod: InstalledMod,
    loser_mod: InstalledMod,
    game: Game,
    session: Session,
) -> list[RenameAction]:
    """Compute renames needed so *loser_mod*'s archives sort after *winner_mod*'s.

    Since first-loaded wins, the winner must sort before the loser.  We demote
    the loser by adding a ``zz_`` prefix to its archives.
    """
    winner_files = _get_mod_archive_files(winner_mod)
    loser_files = _get_mod_archive_files(loser_mod)

    if not winner_files or not loser_files:
        return []

    loser_filenames = [f.relative_path.replace("\\", "/").rsplit("/", 1)[-1] for f in loser_files]
    winner_filenames = [f.relative_path.replace("\\", "/").rsplit("/", 1)[-1] for f in winner_files]

    loser_min = min(fn.lower() for fn in loser_filenames)
    winner_max = max(fn.lower() for fn in winner_filenames)

    # Already in correct order — loser sorts after all winner archives
    if loser_min > winner_max:
        return []

    prefix = _compute_prefix(max(winner_filenames, key=lambda fn: fn.lower()))

    # Collect all existing archive filenames for this game (collision detection)
    all_archive_files = session.exec(
        select(InstalledModFile)
        .join(InstalledMod)
        .where(
            InstalledMod.game_id == game.id,
            InstalledModFile.relative_path.like("archive/pc/mod/%"),  # type: ignore[union-attr]
        )
    ).all()
    existing_filenames = {
        f.relative_path.replace("\\", "/").rsplit("/", 1)[-1].lower() for f in all_archive_files
    }

    renames: list[RenameAction] = []
    for f in loser_files:
        rel = f.relative_path.replace("\\", "/")
        old_filename = rel.rsplit("/", 1)[-1]
        stripped = _strip_load_order_prefix(old_filename)
        new_filename = prefix + stripped

        # Collision check — disambiguate with mod_id suffix if needed
        if (
            new_filename.lower() in existing_filenames
            and new_filename.lower() != old_filename.lower()
        ):
            stem = new_filename.rsplit(".", 1)[0]
            ext = new_filename.rsplit(".", 1)[1]
            new_filename = f"{stem}_{loser_mod.id}.{ext}"

        if new_filename == old_filename:
            continue

        new_rel = _ARCHIVE_DIR + new_filename
        renames.append(
            RenameAction(
                old_relative_path=rel,
                new_relative_path=new_rel,
                old_filename=old_filename,
                new_filename=new_filename,
                owning_mod_id=loser_mod.id,  # type: ignore[arg-type]
                owning_mod_name=loser_mod.name,
            )
        )

    return renames


def apply_prefer_mod(
    winner_mod: InstalledMod,
    loser_mod: InstalledMod,
    game: Game,
    session: Session,
    *,
    dry_run: bool = False,
) -> PreferModResult:
    """Rename archives so *winner_mod* wins over *loser_mod*.

    The loser's archives are demoted (``zz_`` prefix) so they sort after
    the winner.  With ``dry_run=True`` the plan is returned without touching
    the filesystem.  On failure, completed renames are rolled back.
    """
    renames = generate_prefer_renames(winner_mod, loser_mod, game, session)

    if not renames:
        return PreferModResult(
            success=True,
            renames=renames,
            dry_run=dry_run,
            message="No renames needed; loser already sorts after winner",
        )

    if dry_run:
        return PreferModResult(
            success=True,
            renames=renames,
            dry_run=True,
            message=f"Dry run: {len(renames)} rename(s) planned",
        )

    game_dir = Path(game.install_path)

    # Validation pass
    for r in renames:
        src = game_dir / r.old_relative_path
        if not src.exists():
            return PreferModResult(
                success=False,
                renames=[],
                dry_run=False,
                message=f"Source file not found: {r.old_relative_path}",
            )
        dst = game_dir / r.new_relative_path
        if dst.exists():
            return PreferModResult(
                success=False,
                renames=[],
                dry_run=False,
                message=f"Target already exists: {r.new_relative_path}",
            )

    # Execute renames with rollback tracking
    completed: list[tuple[Path, Path]] = []
    try:
        for r in renames:
            src = game_dir / r.old_relative_path
            dst = game_dir / r.new_relative_path
            src.rename(dst)
            completed.append((dst, src))  # (new, old) for rollback
    except OSError as exc:
        logger.error("Rename failed: %s", exc)
        rollback_ok = _rollback_renames(completed)
        return PreferModResult(
            success=False,
            renames=renames,
            dry_run=False,
            message=f"Rename failed: {exc}",
            rollback_performed=rollback_ok,
        )

    # Update DB paths — rollback filesystem if DB commit fails
    try:
        for r in renames:
            file_record = session.exec(
                select(InstalledModFile).where(
                    InstalledModFile.installed_mod_id == r.owning_mod_id,
                    InstalledModFile.relative_path == r.old_relative_path,
                )
            ).first()
            if file_record:
                file_record.relative_path = r.new_relative_path
                session.add(file_record)
            else:
                logger.warning(
                    "DB record not found for %s (mod_id=%s); filesystem renamed but DB not updated",
                    r.old_relative_path,
                    r.owning_mod_id,
                )

        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("DB update failed after renames: %s — rolling back filesystem", exc)
        _rollback_renames(completed)
        return PreferModResult(
            success=False,
            renames=renames,
            dry_run=False,
            message=f"DB update failed after filesystem renames: {exc}",
            rollback_performed=True,
        )

    return PreferModResult(
        success=True,
        renames=renames,
        dry_run=False,
        message=f"Applied {len(renames)} rename(s) successfully",
    )
