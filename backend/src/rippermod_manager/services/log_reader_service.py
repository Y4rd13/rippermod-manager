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
# Map spdlog's level aliases; "critical" is the most severe spdlog level (e.g.
# RED4ext crash reports) — surface it as an error rather than dropping it.
_LEVEL_NORMALIZE = {"warn": "warning", "err": "error", "critical": "error"}
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


# --- attribution: map an error line to the installed mod that owns the file ---

_KNOWN_ROOTS = ("archive/", "bin/", "engine/", "mods/", "r6/", "red4ext/")
_REDS_RE = re.compile(r"[\w\-./\\:]+\.reds", re.IGNORECASE)
_DLL_RE = re.compile(r"red4ext[\\/]plugins[\\/][^\s'\"]+?\.dll", re.IGNORECASE)
_CET_MODS_RE = re.compile(r"mods[\\/]([\w\-.]+)", re.IGNORECASE)
_READING_RE = re.compile(r'Reading "(?P<path>[^"]+\.ya?ml)"', re.IGNORECASE)


def _strip_base(token: str, base_low: str) -> str:
    p = token.strip().strip('"').replace("\\", "/").lower().lstrip("/")
    if base_low and p.startswith(base_low + "/"):
        p = p[len(base_low) + 1 :]
    return p


def _candidate_path(label: str, msg: str, last_yaml: str | None, base_low: str) -> str | None:
    """A game-relative path (lowercase, forward slashes) extracted from an error
    line, matching the ownership map's keys -- or None when the line carries no
    attributable on-disk path (ArchiveXL depot paths, TweakXL record names, ...)."""
    if label == "redscript":
        m = _REDS_RE.search(msg)
        if not m:
            return None
        p = _strip_base(m.group(0), base_low)
        if not p.endswith(".reds"):
            return None
        # bare paths in redscript errors are relative to r6/scripts
        return p if p.startswith(_KNOWN_ROOTS) else f"r6/scripts/{p}"
    if label == "RED4ext":
        m = _DLL_RE.search(msg)
        return _strip_base(m.group(0), base_low) if m else None
    if label == "TweakXL":
        # the error names a TweakDB record, not a path; attribute to the file the
        # most recent "Reading "<x>.yaml"" line announced (same log, in order).
        return f"r6/tweaks/{last_yaml}" if last_yaml else None
    if label.startswith("CET"):
        m = _CET_MODS_RE.search(msg)
        return f"bin/x64/plugins/cyber_engine_tweaks/mods/{m.group(1).lower()}" if m else None
    return None  # ArchiveXL, Codeware: no reliable on-disk path in the message


def _owner_of(candidate: str, owners: dict[str, str]) -> str | None:
    """Exact path match, then a directory-prefix match (for CET mod folders)."""
    name = owners.get(candidate)
    if name:
        return name
    prefix = candidate.rstrip("/") + "/"
    for path, owner in owners.items():
        if path.startswith(prefix):
            return owner
    return None


def read_log_errors(
    install_path: str, owners: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Parse warnings/errors from the known framework logs under ``install_path``.

    Returns up to ``_MAX_ERRORS`` entries, grouped by source (registry order),
    newest first within each source. Synchronous (blocking file reads).

    When ``owners`` (a game-relative-path -> mod-name map, e.g. from
    ``install_service.get_file_ownership_map``) is given, each error whose line
    carries a matchable on-disk path is attributed to the owning mod
    (``mod_name``). Attribution is best-effort and never guesses -- a miss leaves
    ``mod_name`` None; ArchiveXL/Codeware lines (depot paths) stay unattributed.
    """
    base = Path(install_path)
    base_low = str(base).replace("\\", "/").lower().rstrip("/")
    errors: list[dict[str, Any]] = []
    for label, rel, fmt, is_glob in _SOURCES:
        path = _resolve_log(base, rel, is_glob)
        if path is None:
            continue
        pattern = _PARSERS[fmt]
        matched: list[dict[str, Any]] = []
        last_yaml: str | None = None  # TweakXL: most recent "Reading <x>.yaml"
        for raw in _read_tail(path, _MAX_LINES):
            parsed = _match(pattern, raw.rstrip("\n"))
            if parsed is None:
                continue
            level, ts, msg = parsed
            if label == "TweakXL":
                rm = _READING_RE.search(msg)
                if rm:
                    last_yaml = rm.group("path").replace("\\", "/").lower()
            level = _LEVEL_NORMALIZE.get(level, level)
            if level not in _KEEP:
                continue
            mod_name: str | None = None
            if owners:
                cand = _candidate_path(label, msg, last_yaml, base_low)
                if cand:
                    mod_name = _owner_of(cand, owners)
            matched.append(
                {
                    "source": label,
                    "level": level,
                    "timestamp": ts,
                    "message": msg.strip(),
                    "mod_name": mod_name,
                }
            )
        matched.reverse()  # newest first within this source
        errors.extend(matched[:_MAX_PER_SOURCE])
        if len(errors) >= _MAX_ERRORS:
            break
    return errors[:_MAX_ERRORS]
