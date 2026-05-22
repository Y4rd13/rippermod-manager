"""Framework mod monitor.

Detect the core Cyberpunk 2077 modding frameworks on disk, read their installed
version, and (best-effort) compare against the latest version on Nexus.

Disk reads use ``pefile`` (same pattern as ``services/game_version.py``) and are
synchronous — async callers offload them via ``run_in_threadpool``. The Nexus
lookup is a single read-only GraphQL batch and is best-effort: any failure
leaves the report with on-disk state only.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any

import httpx
import pefile

from rippermod_manager.constants import FRAMEWORKS
from rippermod_manager.nexus.client import NexusPremiumRequiredError, NexusRateLimitError
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
from rippermod_manager.services.nexus_helpers import graphql_mod_to_rest_info

logger = logging.getLogger(__name__)


def _clean_semver(value: str | None) -> str | None:
    """Extract a clean dotted-numeric version: drop a leading ``v`` and any
    suffix like ``[HEAD]`` or build metadata. Returns None if not version-like."""
    if not value:
        return None
    token = value.strip().lstrip("vV").split(" ")[0].split("+")[0]
    parts = token.split(".")
    if not token or not parts[0].isdigit():
        return None
    return token


def _read_pe_version(path: Path) -> str | None:
    """Read a clean semver from a PE file's version resource (DLL/exe/asi).

    Prefers ProductVersion (clean for the XL-family plugins), falls back to
    FileVersion. Mirrors the pefile pattern in services/game_version.py.
    """
    pe = None
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )
        product: str | None = None
        file_v: str | None = None
        for fi in getattr(pe, "FileInfo", []) or []:
            for entry in fi:
                if getattr(entry, "Key", b"") != b"StringFileInfo":
                    continue
                for stab in entry.StringTable:
                    for key_b, val_b in stab.entries.items():
                        key = key_b.decode(errors="replace")
                        if key == "ProductVersion":
                            product = val_b.decode(errors="replace")
                        elif key == "FileVersion":
                            file_v = val_b.decode(errors="replace")
        return _clean_semver(product) or _clean_semver(file_v)
    except (OSError, AttributeError, pefile.PEFormatError):
        logger.warning("Failed to read PE version from %s", path, exc_info=True)
        return None
    finally:
        if pe is not None:
            with contextlib.suppress(Exception):
                pe.close()


def detect_frameworks(install_path: str) -> list[dict[str, Any]]:
    """Detect each framework on disk (marker present) and its installed version.

    Synchronous (blocking file I/O). redscript has no on-disk version source, so
    its version stays None.
    """
    base = Path(install_path)
    results: list[dict[str, Any]] = []
    for fw in FRAMEWORKS:
        marker = base.joinpath(*fw["marker"].split("/"))
        installed = marker.exists()
        version = _read_pe_version(marker) if installed and fw["version_kind"] == "pe" else None
        results.append(
            {
                "key": fw["key"],
                "name": fw["display_name"],
                "nexus_mod_id": fw["nexus_mod_id"],
                "installed": installed,
                "version": version,
                "version_known": version is not None,
            }
        )
    return results


async def fetch_latest_versions(
    game_domain: str, gql: NexusGraphQLClient, mod_ids: list[int]
) -> dict[int, str]:
    """Latest version per Nexus mod id via one GraphQL batch. Best-effort:
    returns {} on any Nexus/HTTP error so the endpoint still reports disk state."""
    if not mod_ids:
        return {}
    try:
        batch = await gql.batch_mods(game_domain, mod_ids)
    except (NexusRateLimitError, NexusPremiumRequiredError, httpx.HTTPError):
        logger.warning("framework latest-version lookup failed", exc_info=True)
        return {}
    latest: dict[int, str] = {}
    for mod_id, gql_mod in batch.items():
        raw = graphql_mod_to_rest_info(gql_mod).get("version") or ""
        # Normalize like the on-disk version so display + comparison stay consistent.
        version = _clean_semver(raw) or raw
        if version:
            latest[mod_id] = version
    return latest
