"""Mod error reader.

Reads the modding frameworks' log files and surfaces their warnings/errors in
one place, per game. The logs are the source of truth — read on demand, no
persistence.

Parsers are deliberately tolerant: a line that doesn't match a known format is
skipped, never raised. The formats are external/undocumented and change across
framework versions, so tolerance is the whole point.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_LINES = 4000  # tail size read per log (logs grow large)
_MAX_ERRORS = 300  # cap on total returned entries
_MAX_PER_SOURCE = 50  # cap per source so one noisy log can't drown the others

# --- per-format line parsers: return (level, timestamp, message) or None ---

# spdlog (RED4ext + its plugins): "[ts] [name-or-pid] [level] message"
_SPDLOG_RE = re.compile(r"^\[(?P<ts>[\d\-: .]+)\] \[[^\]]*\] \[(?P<level>\w+)\] (?P<msg>.*)$")
# CET: "[ts UTC±hh:mm] [level] [func] [pid] message"
_CET_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] \[(?P<level>\w+)\] \[[^\]]*\] \[\d+\] (?P<msg>.*)$")
# redscript: "[LEVEL - date] message"  (level uppercase)
_REDSCRIPT_RE = re.compile(r"^\[(?P<level>[A-Z]+) - (?P<ts>[^\]]+)\] (?P<msg>.*)$")


def _match(pattern: re.Pattern[str], line: str) -> tuple[str, str, str] | None:
    m = pattern.match(line)
    if not m:
        return None
    ts = m.groupdict().get("ts") or ""
    return m.group("level").lower(), ts, m.group("msg")


_PARSERS: dict[str, re.Pattern[str]] = {
    "spdlog": _SPDLOG_RE,
    "cet": _CET_RE,
    "redscript": _REDSCRIPT_RE,
}
_LEVEL_NORMALIZE = {"warn": "warning", "err": "error"}
_KEEP = {"error", "warning"}

# (label, relative path or glob under the install, format key, is_glob)
_SOURCES: list[tuple[str, str, str, bool]] = [
    ("redscript", "r6/logs/redscript_rCURRENT.log", "redscript", False),
    ("RED4ext", "red4ext/logs/red4ext-*.log", "spdlog", True),
    ("CET", "bin/x64/plugins/cyber_engine_tweaks/cyber_engine_tweaks.log", "cet", False),
    ("CET (scripting)", "bin/x64/plugins/cyber_engine_tweaks/scripting.log", "cet", False),
    ("ArchiveXL", "red4ext/plugins/ArchiveXL/ArchiveXL.log", "spdlog", False),
    ("TweakXL", "red4ext/plugins/TweakXL/TweakXL.log", "spdlog", False),
    ("Codeware", "red4ext/plugins/Codeware/Codeware.log", "spdlog", False),
]


def _resolve_log(base: Path, rel: str, is_glob: bool) -> Path | None:
    if is_glob:
        try:
            matches = sorted(base.glob(rel), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return None
        return matches[0] if matches else None
    path = base.joinpath(*rel.split("/"))
    return path if path.is_file() else None


def _read_tail(path: Path, max_lines: int) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return list(deque(fh, maxlen=max_lines))
    except OSError:
        logger.warning("could not read log %s", path, exc_info=True)
        return []


def read_log_errors(install_path: str) -> list[dict[str, Any]]:
    """Parse warnings/errors from the known framework logs under ``install_path``.

    Returns up to ``_MAX_ERRORS`` entries, grouped by source (registry order),
    newest first within each source. Synchronous (blocking file reads).
    """
    base = Path(install_path)
    errors: list[dict[str, Any]] = []
    for label, rel, fmt, is_glob in _SOURCES:
        path = _resolve_log(base, rel, is_glob)
        if path is None:
            continue
        pattern = _PARSERS[fmt]
        matched: list[dict[str, Any]] = []
        for raw in _read_tail(path, _MAX_LINES):
            parsed = _match(pattern, raw.rstrip("\n"))
            if parsed is None:
                continue
            level, ts, msg = parsed
            level = _LEVEL_NORMALIZE.get(level, level)
            if level not in _KEEP:
                continue
            matched.append(
                {
                    "source": label,
                    "level": level,
                    "timestamp": ts,
                    "message": msg.strip(),
                    "mod_name": None,
                }
            )
        matched.reverse()  # newest first within this source
        errors.extend(matched[:_MAX_PER_SOURCE])
        if len(errors) >= _MAX_ERRORS:
            break
    return errors[:_MAX_ERRORS]
