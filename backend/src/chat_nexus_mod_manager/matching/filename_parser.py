"""Parse Nexus Mods download filenames to extract mod metadata.

Nexus download filenames follow predictable patterns:
  ModName-{nexus_id}-{version}-{timestamp}.ext
  {nexus_id}-ModName.ext
  ModName.ext

This module provides a fast heuristic that can skip expensive ML-based
matching when the filename already encodes the Nexus mod ID.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedFilename:
    nexus_mod_id: int | None
    name: str
    version: str | None
    upload_timestamp: int | None


# Pattern 1: Nexus download format
# Examples:
#   "CET 1.37.1-107-1-37-1-1759193708"
#   "Mod Name-12345-2-0-0-1750000000"
_NEXUS_RE = re.compile(
    r"^(.+?)"  # mod name (non-greedy)
    r"-(\d{1,6})"  # nexus mod id (1-6 digits)
    r"-([vV]?\d[\da-zA-Z\-]*[\da-zA-Z]|[vV]?\d)"  # version
    r"-(\d{8,})$"  # upload timestamp (8+ digits)
)

# Pattern 2: Simple id-name format
# Examples: "107-CyberEngineTweaks", "12345_SomeMod"
_SIMPLE_RE = re.compile(r"^(\d+)[-_](.+)$")


def parse_mod_filename(filename: str) -> ParsedFilename:
    """Parse a mod archive filename and extract Nexus metadata.

    Supports three filename formats in order of specificity:
    1. Full Nexus: ``ModName-{id}-{version}-{timestamp}.ext``
    2. Simple: ``{id}-ModName.ext`` or ``{id}_ModName.ext``
    3. Plain: ``ModName.ext`` (no metadata extracted)
    """
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename

    match = _NEXUS_RE.match(stem)
    if match:
        version_raw = match.group(3)
        version = version_raw.replace("-", ".")
        return ParsedFilename(
            nexus_mod_id=int(match.group(2)),
            name=match.group(1).strip(),
            version=version,
            upload_timestamp=int(match.group(4)),
        )

    match = _SIMPLE_RE.match(stem)
    if match:
        return ParsedFilename(
            nexus_mod_id=int(match.group(1)),
            name=match.group(2).strip(),
            version=None,
            upload_timestamp=None,
        )

    return ParsedFilename(
        nexus_mod_id=None,
        name=stem.strip(),
        version=None,
        upload_timestamp=None,
    )


def parse_version(version_str: str) -> list[tuple[int, str]]:
    """Parse a version string into comparable (numeric, suffix) parts.

    Handles formats like ``1.2.3``, ``1.0.0-beta``, ``2.1.1a``.
    Parts are split on ``.``, ``-``, and ``_``.
    """
    if not version_str:
        return []

    parts = re.split(r"[.\-_]", version_str.lower().strip())
    result: list[tuple[int, str]] = []

    for part in parts:
        m = re.match(r"^(\d+)(.*)$", part)
        if m:
            result.append((int(m.group(1)), m.group(2)))
        elif part:
            result.append((-1, part))

    return result


def is_newer_version(latest: str, installed: str) -> bool:
    """Return True if *latest* is strictly newer than *installed*.

    Uses numeric comparison (not lexicographic) so ``0.15.0 > 0.2.0``.
    A release version beats a prerelease: ``1.0 > 1.0-beta``.
    """
    latest_parts = parse_version(latest)
    installed_parts = parse_version(installed)

    if not latest_parts or not installed_parts:
        return latest != installed

    max_len = max(len(latest_parts), len(installed_parts))
    while len(latest_parts) < max_len:
        latest_parts.append((0, ""))
    while len(installed_parts) < max_len:
        installed_parts.append((0, ""))

    for (lat_num, lat_str), (inst_num, inst_str) in zip(
        latest_parts, installed_parts, strict=False
    ):
        if lat_num > inst_num:
            return True
        if lat_num < inst_num:
            return False
        if lat_str == "" and inst_str != "":
            return True
        if lat_str != "" and inst_str == "":
            return False
        if lat_str > inst_str:
            return True
        if lat_str < inst_str:
            return False

    return False
