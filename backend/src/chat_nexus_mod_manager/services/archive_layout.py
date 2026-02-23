"""Archive layout detection for root-folder stripping and FOMOD flagging.

Analyses the top-level directory structure of a mod archive to decide
whether a wrapper folder should be stripped during install, or whether the
archive is a FOMOD installer that cannot be auto-installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from chat_nexus_mod_manager.constants import GAME_REGISTRY


class ArchiveLayout(StrEnum):
    STANDARD = "standard"
    WRAPPED = "wrapped"
    FOMOD = "fomod"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LayoutResult:
    layout: ArchiveLayout
    strip_prefix: str | None = None


def known_roots_for_game(domain_name: str) -> set[str]:
    """Return the set of known top-level mod directories for a game.

    Extracts the first path component from each ``mod_paths`` entry in
    ``GAME_REGISTRY``.  Returns an empty set for unknown games.
    """
    entry = GAME_REGISTRY.get(domain_name)
    if not entry:
        return set()
    roots: set[str] = set()
    for rel_path, _, _ in entry["mod_paths"]:
        first = PurePosixPath(rel_path).parts[0].lower()
        roots.add(first)
    return roots


def detect_layout(
    entries: list[object],
    known_roots: set[str],
) -> LayoutResult:
    """Classify an archive's layout from its file/directory entries.

    Parameters
    ----------
    entries:
        Objects with ``filename: str`` and ``is_dir: bool`` attributes
        (typically ``ArchiveEntry`` instances).
    known_roots:
        Lower-cased set of recognised game root directories
        (e.g. ``{"archive", "bin", "r6", "red4ext", "mods"}``).

    Returns
    -------
    LayoutResult
        The detected layout and, for ``WRAPPED`` archives, the prefix to
        strip from every entry path.
    """
    if not entries:
        return LayoutResult(layout=ArchiveLayout.UNKNOWN)

    top_level_dirs: set[str] = set()
    has_root_file = False
    has_fomod_config = False
    second_level_dirs: set[str] = set()

    for entry in entries:
        filename: str = entry.filename  # type: ignore[union-attr]
        normalised = filename.replace("\\", "/").strip("/")
        if not normalised:
            continue

        parts = PurePosixPath(normalised).parts

        # Check for fomod/ModuleConfig.xml at any depth
        lower_parts = [p.lower() for p in parts]
        for i, part in enumerate(lower_parts):
            if (
                part == "fomod"
                and i + 1 < len(lower_parts)
                and lower_parts[i + 1] == "moduleconfig.xml"
            ):
                has_fomod_config = True
                break

        first = parts[0].lower()

        if len(parts) == 1 and not getattr(entry, "is_dir", False):
            has_root_file = True
        else:
            top_level_dirs.add(first)

        if len(parts) >= 2:
            second_level_dirs.add(parts[1].lower())

    # 1. Any top-level component matches a known game root -> STANDARD
    if known_roots and top_level_dirs & known_roots:
        return LayoutResult(layout=ArchiveLayout.STANDARD)

    # 2. FOMOD detected
    if has_fomod_config:
        return LayoutResult(layout=ArchiveLayout.FOMOD)

    # 3. Single wrapper directory, no loose root files, second-level has known roots
    if (
        len(top_level_dirs) == 1
        and not has_root_file
        and known_roots
        and second_level_dirs & known_roots
    ):
        wrapper = next(iter(top_level_dirs))
        # Recover the original-case prefix from the first entry that matches
        for entry in entries:
            filename = entry.filename.replace("\\", "/").strip("/")  # type: ignore[union-attr]
            if filename:
                original_first = PurePosixPath(filename).parts[0]
                if original_first.lower() == wrapper:
                    return LayoutResult(
                        layout=ArchiveLayout.WRAPPED,
                        strip_prefix=original_first,
                    )

    return LayoutResult(layout=ArchiveLayout.UNKNOWN)
