"""Filesystem-safe naming helpers for VFS staging directories.

Extracted to a shared module so the three callers (install_service,
fomod_install_service, vfs.migration) cannot diverge. Lives under
``services/vfs/`` because that package has no dependencies on the install
services, avoiding the circular-import issue that originally forced each
caller to duplicate the helpers.
"""

from __future__ import annotations

import re
from pathlib import Path


def safe_dir_name(name: str) -> str:
    """Sanitise a mod name into a filesystem-safe directory name.

    Replaces any character outside ``[A-Za-z0-9._-]`` with ``_``, trims
    leading/trailing underscores, and returns ``"mod"`` for the empty result.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "mod"


def unique_staging_name(staging_root: Path, base_name: str) -> str:
    """Return a subdir name under ``staging_root`` that does not yet exist.

    Two mods whose names sanitise to the same string (e.g. "My Cool Mod!"
    and "My Cool Mod?") would otherwise share a staging directory and corrupt
    each other. Appends ``_2``, ``_3``, ... when a collision is detected.
    """
    safe = safe_dir_name(base_name)
    candidate = safe
    n = 1
    while (staging_root / candidate).exists():
        n += 1
        candidate = f"{safe}_{n}"
    return candidate
