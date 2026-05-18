"""PID-file helpers for detecting orphaned backend instances.

When the Tauri parent dies ungracefully (force-quit, crash, task manager),
its PyInstaller-spawned backend child can survive as an orphan still bound
to port 8425.  The next Tauri launch then can't bind the port and the new
backend self-shuts-down (FastAPI lifespan logs ``Application started``
immediately followed by ``Shutting down``).

We write the backend's PID on startup so the Tauri shell can detect this
state on the next launch and kill the orphan before spawning a fresh
sidecar.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

PID_FILENAME = "rmm-backend.pid"


def pid_path(data_dir: Path) -> Path:
    return data_dir / PID_FILENAME


def write_pid_file(data_dir: Path) -> None:
    """Write ``os.getpid()`` to ``<data_dir>/rmm-backend.pid``.

    Best-effort; logs and continues if the write fails so a transient
    filesystem error never blocks app startup.
    """
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        pid_path(data_dir).write_text(str(os.getpid()), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write PID file: %s", exc)


def remove_pid_file(data_dir: Path) -> None:
    """Remove the PID file if present.  Idempotent."""
    try:
        path = pid_path(data_dir)
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.warning("Could not remove PID file: %s", exc)
