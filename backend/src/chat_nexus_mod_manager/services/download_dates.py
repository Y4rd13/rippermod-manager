"""Shared helpers for resolving archive download dates."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from chat_nexus_mod_manager.models.download import DownloadJob


def archive_download_dates(
    session: Session,
    game_id: int,
    install_path: str,
    filenames: set[str],
) -> dict[str, datetime]:
    """Return filename → download datetime for a set of archive filenames.

    Looks up ``DownloadJob.completed_at`` first, then falls back to the
    archive file's ``st_mtime`` on disk.
    """
    if not filenames:
        return {}

    dl_rows = session.exec(
        select(DownloadJob.file_name, DownloadJob.completed_at).where(
            DownloadJob.game_id == game_id,
            DownloadJob.status == "completed",
            DownloadJob.completed_at.is_not(None),  # type: ignore[union-attr]
            DownloadJob.file_name.in_(filenames),  # type: ignore[union-attr]
        )
    ).all()

    result: dict[str, datetime] = {}
    for fn, completed in dl_rows:
        if fn and completed:
            existing = result.get(fn)
            if existing is None or completed > existing:
                result[fn] = completed

    # File mtime fallback for archives not in DownloadJob
    staging = Path(install_path) / "downloaded_mods"
    for fn in filenames - result.keys():
        try:
            mtime = os.stat(staging / fn).st_mtime
            result[fn] = datetime.fromtimestamp(mtime, tz=UTC)
        except OSError:
            continue

    return result
