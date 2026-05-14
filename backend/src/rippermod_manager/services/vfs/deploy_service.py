"""Orchestrates VFS deployment: planning, journaling, execution."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from rippermod_manager.models.game import Game
from rippermod_manager.schemas.deploy import PreflightReport
from rippermod_manager.services.vfs.primitives import (
    is_game_running,
    probe_hardlink_support,
    same_volume,
)

logger = logging.getLogger(__name__)

GAME_EXE = "Cyberpunk2077.exe"


def pre_flight_check(game: Game) -> PreflightReport:
    report = PreflightReport()
    install = Path(game.install_path)
    staging = install / "downloaded_mods"
    staging.mkdir(parents=True, exist_ok=True)

    if is_game_running(GAME_EXE):
        report.ok = False
        report.game_running = True
        report.reasons.append("Cyberpunk 2077 is running — close it before deploying.")

    try:
        sv = same_volume(staging, install)
    except Exception as exc:  # file I/O can raise many OSError subclasses
        sv = False
        report.reasons.append(f"could not check volume: {exc}")
    report.same_volume = sv
    if not sv:
        report.ok = False
        report.reasons.append(
            "Staging dir and game dir are on different volumes; hardlinks require same volume."
        )

    try:
        report.hardlink_supported = probe_hardlink_support(staging, install)
    except Exception as exc:  # probe touches filesystem; wide catch intentional
        report.hardlink_supported = False
        report.reasons.append(f"hardlink probe failed: {exc}")
    if not report.hardlink_supported:
        report.ok = False
        report.reasons.append("Filesystem does not support hardlinks (NTFS required).")

    try:
        report.free_disk_bytes = shutil.disk_usage(install).free
    except OSError:
        report.free_disk_bytes = 0

    return report
