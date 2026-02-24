"""FOMOD file list computation and extraction.

Computes the final list of files to install based on parsed FOMOD config
and user selections, then extracts them to the game directory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.archive.handler import ArchiveEntry, open_archive
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.schemas.install import InstallResult
from rippermod_manager.services.fomod_config_parser import (
    CompositeDependency,
    DependencyOperator,
    FileMapping,
    FileState,
    FomodConfig,
)
from rippermod_manager.services.install_service import get_file_ownership_map

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedFile:
    archive_path: str
    game_relative_path: str
    priority: int
    doc_order: int = 0


# ---------------------------------------------------------------------------
# Dependency evaluation
# ---------------------------------------------------------------------------


def evaluate_dependency(
    dependency: CompositeDependency,
    flags: dict[str, str],
    installed_files: set[str] | None = None,
) -> bool:
    """Recursively evaluate a composite dependency against current flags."""
    results: list[bool] = []

    for fc in dependency.flag_conditions:
        results.append(flags.get(fc.name, "") == fc.value)

    for file_cond in dependency.file_conditions:
        file_lower = file_cond.file.lower()
        file_exists = file_lower in (installed_files or set())
        if file_cond.state == FileState.ACTIVE:
            results.append(file_exists)
        elif file_cond.state in (FileState.INACTIVE, FileState.MISSING):
            results.append(not file_exists)

    for nested in dependency.nested:
        results.append(evaluate_dependency(nested, flags, installed_files))

    if not results:
        return True

    if dependency.operator == DependencyOperator.AND:
        return all(results)
    return any(results)


def is_step_visible(
    step_visible: CompositeDependency | None,
    flags: dict[str, str],
    installed_files: set[str] | None = None,
) -> bool:
    """Check if a step should be shown based on its visibility conditions."""
    if step_visible is None:
        return True
    return evaluate_dependency(step_visible, flags, installed_files)


# ---------------------------------------------------------------------------
# File expansion
# ---------------------------------------------------------------------------


def _build_entry_map(
    archive_entries: list[ArchiveEntry],
    fomod_prefix: str,
) -> dict[str, str]:
    """Build a lowercased map of relative-to-fomod-prefix -> original entry path."""
    entry_map: dict[str, str] = {}
    prefix_lower = fomod_prefix.lower().rstrip("/")
    prefix_with_slash = prefix_lower + "/" if prefix_lower else ""

    for entry in archive_entries:
        if entry.is_dir:
            continue
        normalised = entry.filename.replace("\\", "/")
        lower = normalised.lower()
        if prefix_with_slash and lower.startswith(prefix_with_slash):
            relative = normalised[len(prefix_with_slash) :]
        elif not prefix_with_slash:
            relative = normalised
        else:
            continue
        entry_map[relative.lower()] = entry.filename
    return entry_map


def expand_folder_mapping(
    mapping: FileMapping,
    entry_map: dict[str, str],
) -> list[ResolvedFile]:
    """Expand a folder mapping to individual file entries."""
    source_lower = mapping.source.lower().rstrip("/")
    source_prefix = source_lower + "/" if source_lower else ""
    results: list[ResolvedFile] = []

    for relative_lower, original_path in entry_map.items():
        if source_prefix and not relative_lower.startswith(source_prefix):
            continue
        if not source_prefix and source_lower:
            continue

        sub_path = relative_lower[len(source_prefix) :] if source_prefix else relative_lower
        game_path = f"{mapping.destination}/{sub_path}" if mapping.destination else sub_path

        results.append(
            ResolvedFile(
                archive_path=original_path,
                game_relative_path=game_path,
                priority=mapping.priority,
            )
        )
    return results


def expand_file_mapping(
    mapping: FileMapping,
    entry_map: dict[str, str],
) -> ResolvedFile | None:
    """Expand a single file mapping to a resolved file entry."""
    source_lower = mapping.source.lower()
    original_path = entry_map.get(source_lower)
    if original_path is None:
        logger.warning("FOMOD file mapping source not found in archive: %s", mapping.source)
        return None

    if mapping.destination:
        game_path = mapping.destination
    else:
        # Use the source filename (last component)
        parts = mapping.source.split("/")
        game_path = parts[-1] if parts else mapping.source

    return ResolvedFile(
        archive_path=original_path,
        game_relative_path=game_path,
        priority=mapping.priority,
    )


def _expand_mappings(
    mappings: list[FileMapping],
    entry_map: dict[str, str],
    doc_order_start: int,
) -> tuple[list[ResolvedFile], int]:
    """Expand a list of file mappings, assigning doc_order to each."""
    results: list[ResolvedFile] = []
    order = doc_order_start

    for mapping in mappings:
        if mapping.is_folder:
            expanded = expand_folder_mapping(mapping, entry_map)
            for rf in expanded:
                results.append(
                    ResolvedFile(
                        archive_path=rf.archive_path,
                        game_relative_path=rf.game_relative_path,
                        priority=rf.priority,
                        doc_order=order,
                    )
                )
                order += 1
        else:
            rf = expand_file_mapping(mapping, entry_map)
            if rf is not None:
                results.append(
                    ResolvedFile(
                        archive_path=rf.archive_path,
                        game_relative_path=rf.game_relative_path,
                        priority=rf.priority,
                        doc_order=order,
                    )
                )
                order += 1

    return results, order


# ---------------------------------------------------------------------------
# File list computation
# ---------------------------------------------------------------------------


def compute_file_list(
    config: FomodConfig,
    selections: dict[int, dict[int, list[int]]],
    archive_entries: list[ArchiveEntry],
    fomod_prefix: str,
) -> list[ResolvedFile]:
    """Compute the final list of files to install based on config and selections.

    Args:
        config: Parsed FOMOD configuration.
        selections: step_index -> group_index -> list of selected plugin indices.
        archive_entries: All entries in the archive.
        fomod_prefix: Prefix path before the fomod/ directory in the archive.

    Returns:
        De-duplicated list of resolved files with priority resolution applied.
    """
    entry_map = _build_entry_map(archive_entries, fomod_prefix)
    all_files: list[ResolvedFile] = []
    doc_order = 0
    flags: dict[str, str] = {}

    # 1. Required install files (always installed)
    expanded, doc_order = _expand_mappings(config.required_install_files, entry_map, doc_order)
    all_files.extend(expanded)

    # 2. Process each visible step
    for step_idx, step in enumerate(config.steps):
        if not is_step_visible(step.visible, flags):
            continue

        step_selections = selections.get(step_idx, {})

        for group_idx, group in enumerate(step.groups):
            selected_indices = step_selections.get(group_idx, [])

            for plugin_idx in selected_indices:
                if plugin_idx < 0 or plugin_idx >= len(group.plugins):
                    continue
                plugin = group.plugins[plugin_idx]

                # Add plugin files
                expanded, doc_order = _expand_mappings(plugin.files, entry_map, doc_order)
                all_files.extend(expanded)

                # Accumulate condition flags
                for flag in plugin.condition_flags:
                    flags[flag.name] = flag.value

    # 3. Evaluate conditional file installs
    for pattern in config.conditional_file_installs:
        if evaluate_dependency(pattern.dependency, flags):
            expanded, doc_order = _expand_mappings(pattern.files, entry_map, doc_order)
            all_files.extend(expanded)

    # 4. Priority resolution: higher priority wins, equal priority -> later doc order wins
    dest_map: dict[str, ResolvedFile] = {}
    for rf in all_files:
        key = rf.game_relative_path.lower()
        existing = dest_map.get(key)
        if (
            existing is None
            or rf.priority > existing.priority
            or (rf.priority == existing.priority and rf.doc_order > existing.doc_order)
        ):
            dest_map[key] = rf

    return list(dest_map.values())


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def install_fomod(
    game: Game,
    archive_path: Path,
    session: Session,
    resolved_files: list[ResolvedFile],
    mod_name: str,
    nexus_mod_id: int | None = None,
) -> InstallResult:
    """Extract resolved FOMOD files to the game directory and record ownership.

    Raises:
        FileNotFoundError: If the archive or game directory doesn't exist.
        ValueError: If a mod with the same name is already installed.
    """
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    game_dir = Path(game.install_path)
    if not game_dir.is_dir():
        raise FileNotFoundError(f"Game directory not found: {game_dir}")

    existing = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.name == mod_name,
        )
    ).first()
    if existing:
        raise ValueError(f"Mod '{mod_name}' is already installed. Uninstall first to reinstall.")

    ownership = get_file_ownership_map(session, game.id)  # type: ignore[arg-type]

    # Build set of archive paths we need to read
    archive_path_set = {rf.archive_path for rf in resolved_files}

    extracted_paths: list[str] = []
    skipped = 0
    overwritten = 0

    with open_archive(archive_path) as archive:
        all_entries = archive.list_entries()
        entries_to_read = [e for e in all_entries if e.filename in archive_path_set]
        file_contents = archive.read_all_files(entries_to_read)

        for rf in resolved_files:
            data = file_contents.get(rf.archive_path)
            if data is None:
                logger.warning("FOMOD: archive entry not found: %s", rf.archive_path)
                skipped += 1
                continue

            target = game_dir / rf.game_relative_path
            if not target.resolve().is_relative_to(game_dir.resolve()):
                logger.warning("FOMOD: skipping path traversal entry: %s", rf.game_relative_path)
                skipped += 1
                continue

            if target.exists():
                overwritten += 1

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            extracted_paths.append(rf.game_relative_path)

            normalised_lower = rf.game_relative_path.replace("\\", "/").lower()
            if normalised_lower in ownership:
                prev_mod = ownership[normalised_lower]
                for f in list(prev_mod.files):
                    if f.relative_path.replace("\\", "/").lower() == normalised_lower:
                        session.delete(f)
                        break

    installed = InstalledMod(
        game_id=game.id,  # type: ignore[arg-type]
        name=mod_name,
        source_archive=archive_path.name,
    )

    if nexus_mod_id is not None:
        installed.nexus_mod_id = nexus_mod_id

    session.add(installed)
    session.flush()

    for rel_path in extracted_paths:
        session.add(
            InstalledModFile(
                installed_mod_id=installed.id,  # type: ignore[arg-type]
                relative_path=rel_path,
            )
        )

    session.commit()
    session.refresh(installed)

    logger.info(
        "FOMOD installed '%s' (%d files, %d overwritten)",
        mod_name,
        len(extracted_paths),
        overwritten,
    )
    return InstallResult(
        installed_mod_id=installed.id,  # type: ignore[arg-type]
        name=mod_name,
        files_extracted=len(extracted_paths),
        files_skipped=skipped,
        files_overwritten=overwritten,
    )
