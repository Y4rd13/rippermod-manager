"""Save game backups.

Snapshots the player's Cyberpunk 2077 save folder before risky operations
(deploy, undeploy, uninstall, disable) and lets the user restore a previous
snapshot. All work is local filesystem I/O via ``shutil`` — no Nexus calls.

The pre-action hook is **best-effort**: a failure here is logged and swallowed
so it never aborts the operation (the same contract as ``redmod_deploy``).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import Session

from rippermod_manager.config import settings
from rippermod_manager.services.settings_helpers import get_setting

if TYPE_CHECKING:
    from rippermod_manager.models.game import Game

logger = logging.getLogger(__name__)

# App-setting keys (managed through the generic /settings endpoint).
ENABLED_KEY = "save_backup_enabled"
PATH_KEY = "save_backup_path"

# Cyberpunk 2077's default save location is identical across Steam/GOG/Epic.
_DEFAULT_SAVE_REL = Path("Saved Games") / "CD Projekt Red" / "Cyberpunk 2077"
CYBERPUNK_DOMAIN = "cyberpunk2077"

MAX_BACKUPS = 15
MANIFEST_NAME = "manifest.json"
_SAVES_SUBDIR = "saves"
# Backup folder names are UTC timestamps; restore handles must match this exactly
# (digits and dashes only — no path separators, so they can't traverse).
_ID_RE = re.compile(r"^\d{8}-\d{6}-\d{6}$")


def _backups_root() -> Path:
    return settings.data_dir / "save_backups"


def is_enabled(session: Session) -> bool:
    """Auto-backup is on by default; only an explicit ``"false"`` disables it."""
    return get_setting(session, ENABLED_KEY) != "false"


def resolve_save_dir(session: Session) -> Path:
    """The folder to back up: the configured override, else the default
    Cyberpunk 2077 path under the user profile."""
    override = get_setting(session, PATH_KEY)
    if override:
        return Path(override)
    return Path(os.path.expanduser("~")) / _DEFAULT_SAVE_REL


def _signature(save_dir: Path) -> str:
    """Cheap content signature — sorted ``relpath:size:mtime_ns`` for every file.
    Lets a backup be skipped when nothing changed since the previous one."""
    parts: list[str] = []
    for p in sorted(save_dir.rglob("*")):
        if p.is_file():
            st = p.stat()
            parts.append(f"{p.relative_to(save_dir).as_posix()}:{st.st_size}:{st.st_mtime_ns}")
    return "\n".join(parts)


def _dir_stats(path: Path) -> tuple[int, int]:
    """Return ``(file_count, total_size_bytes)`` for a directory tree."""
    count = 0
    size = 0
    for p in path.rglob("*"):
        if p.is_file():
            count += 1
            with contextlib.suppress(OSError):
                size += p.stat().st_size
    return count, size


def _read_manifest(backup_dir: Path) -> dict:
    try:
        return json.loads((backup_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _list_backup_dirs() -> list[Path]:
    """Backup directories, most recent first (folder names sort chronologically)."""
    root = _backups_root()
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)


def _backup_dir_for(backup_id: str) -> Path:
    if not _ID_RE.match(backup_id):
        raise ValueError(f"invalid backup id: {backup_id!r}")
    return _backups_root() / backup_id


def list_backups(session: Session) -> list[dict]:
    """All backups as plain dicts (most recent first), read from their manifests."""
    out: list[dict] = []
    for d in _list_backup_dirs():
        m = _read_manifest(d)
        out.append(
            {
                "id": d.name,
                "created_at": m.get("created_at"),
                "reason": m.get("reason"),
                "file_count": m.get("file_count"),
                "size_bytes": m.get("size_bytes"),
            }
        )
    return out


def _prune(keep: int) -> None:
    for d in _list_backup_dirs()[keep:]:
        shutil.rmtree(d, ignore_errors=True)


def create_backup(session: Session, *, reason: str, force: bool = False) -> dict | None:
    """Copy the live save folder into a new timestamped backup directory.

    Returns the backup info, or ``None`` if skipped — either the save folder
    doesn't exist, or (when ``force`` is False) the saves are byte-for-byte
    unchanged since the most recent backup. Enforces ``MAX_BACKUPS`` retention.
    """
    save_dir = resolve_save_dir(session)
    if not save_dir.is_dir():
        logger.info("save backup skipped: no save folder at %s", save_dir)
        return None

    sig = _signature(save_dir)
    if not force:
        existing = _list_backup_dirs()
        if existing and _read_manifest(existing[0]).get("signature") == sig:
            logger.info("save backup skipped: saves unchanged since last backup")
            return None

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    dest = _backups_root() / stamp
    dest.mkdir(parents=True, exist_ok=True)
    saves_dest = dest / _SAVES_SUBDIR
    shutil.copytree(save_dir, saves_dest)

    count, size = _dir_stats(saves_dest)
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "signature": sig,
        "file_count": count,
        "size_bytes": size,
        "source": str(save_dir),
    }
    (dest / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _prune(MAX_BACKUPS)
    logger.info(
        "save backup created at %s (%d files, %d bytes, reason=%s)", dest, count, size, reason
    )
    return {
        "id": stamp,
        "created_at": manifest["created_at"],
        "reason": reason,
        "file_count": count,
        "size_bytes": size,
    }


def restore_backup(session: Session, backup_id: str) -> dict:
    """Restore a backup's saves into the live save folder.

    Refuses while the game is running. Takes a best-effort safety snapshot of the
    current saves first (reason ``"pre-restore"``) so the restore is undoable,
    then copies the backup's files over the live folder — overwriting same-named
    files without deleting saves created after the backup.
    """
    # Lazy import: avoids any import cycle through the vfs package.
    from rippermod_manager.services.vfs.primitives import GameRunningError, is_game_running

    saves_src = _backup_dir_for(backup_id) / _SAVES_SUBDIR
    if not saves_src.is_dir():
        raise FileNotFoundError(f"backup not found: {backup_id}")
    if is_game_running():
        raise GameRunningError("Cyberpunk 2077 is running, close the game before restoring saves.")

    save_dir = resolve_save_dir(session)
    try:
        create_backup(session, reason="pre-restore", force=True)
    except OSError as exc:
        logger.warning("pre-restore safety snapshot failed: %s", exc)

    save_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(saves_src, save_dir, dirs_exist_ok=True)
    logger.info("restored save backup %s into %s", backup_id, save_dir)
    return {"id": backup_id, "restored_to": str(save_dir)}


def maybe_backup_before(game: Game, session: Session, *, reason: str) -> None:
    """Best-effort save snapshot before a risky operation (deploy, undeploy,
    uninstall, disable). Never raises — a backup failure must not abort the
    operation. No-op for non-Cyberpunk games or when disabled. The signature
    dedupe in ``create_backup`` means a run of risky actions with unchanged
    saves yields a single backup."""
    if game.domain_name != CYBERPUNK_DOMAIN or not is_enabled(session):
        return
    try:
        create_backup(session, reason=reason, force=False)
    except OSError as exc:
        logger.warning("%s save backup failed: %s", reason, exc)
