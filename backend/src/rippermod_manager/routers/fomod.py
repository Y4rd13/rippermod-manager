"""FOMOD wizard installer endpoints.

Provides config parsing, file preview, and installation for FOMOD archives.
Nested under the install router prefix: /games/{game_name}/install/fomod/
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from rippermod_manager.archive.handler import ArchiveEntry, open_archive
from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.fomod import (
    FomodConfigOut,
    FomodFileMapping,
    FomodFlagSetter,
    FomodGroupOut,
    FomodInstallRequest,
    FomodPluginOut,
    FomodPreviewFile,
    FomodPreviewRequest,
    FomodPreviewResult,
    FomodStepOut,
    FomodTypeDescriptor,
)
from rippermod_manager.schemas.install import InstallResult
from rippermod_manager.services.fomod_config_parser import FomodConfig, parse_fomod_config
from rippermod_manager.services.fomod_install_service import compute_file_list, install_fomod
from rippermod_manager.services.fomod_parser import inspect_archive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/install/fomod", tags=["fomod"])


def _get_fomod_config(
    game_name: str,
    archive_filename: str,
    session: Session,
) -> tuple[FomodConfig, list[ArchiveEntry], str, Game, Path]:
    """Validate archive path, find ModuleConfig.xml, parse it.

    Returns (config, archive_entries, fomod_prefix, game, archive_path).
    """
    game = get_game_or_404(game_name, session)
    staging = Path(game.install_path) / "downloaded_mods"
    archive_path = staging / archive_filename
    if not archive_path.resolve().is_relative_to(staging.resolve()):
        raise HTTPException(400, "Invalid archive filename")
    if not archive_path.is_file():
        raise HTTPException(404, f"Archive not found: {archive_filename}")

    with open_archive(archive_path) as archive:
        entries = archive.list_entries()

        # Find fomod/ModuleConfig.xml (case-insensitive)
        config_entry = None
        for entry in entries:
            if entry.is_dir:
                continue
            lower = entry.filename.replace("\\", "/").lower()
            if lower.endswith("fomod/moduleconfig.xml"):
                config_entry = entry
                break

        if config_entry is None:
            raise HTTPException(400, "Archive does not contain a FOMOD ModuleConfig.xml")

        # Determine prefix: everything before fomod/
        normalised = config_entry.filename.replace("\\", "/")
        lower = normalised.lower()
        fomod_idx = lower.rfind("fomod/moduleconfig.xml")
        fomod_prefix = normalised[:fomod_idx].rstrip("/") if fomod_idx > 0 else ""

        xml_bytes = archive.read_file(config_entry)

    try:
        config = parse_fomod_config(xml_bytes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return config, entries, fomod_prefix, game, archive_path


def _config_to_out(config: FomodConfig) -> FomodConfigOut:
    """Convert parsed FomodConfig to API response schema."""
    steps = []
    for step in config.steps:
        groups = []
        for group in step.groups:
            plugins = []
            for plugin in group.plugins:
                plugins.append(
                    FomodPluginOut(
                        name=plugin.name,
                        description=plugin.description,
                        image_path=plugin.image_path,
                        files=[
                            FomodFileMapping(
                                source=f.source,
                                destination=f.destination,
                                priority=f.priority,
                                is_folder=f.is_folder,
                            )
                            for f in plugin.files
                        ],
                        condition_flags=[
                            FomodFlagSetter(name=cf.name, value=cf.value)
                            for cf in plugin.condition_flags
                        ],
                        type_descriptor=FomodTypeDescriptor(
                            default_type=plugin.type_descriptor.default_type.value,
                        ),
                    )
                )
            groups.append(
                FomodGroupOut(
                    name=group.name,
                    type=group.type.value,
                    plugins=plugins,
                )
            )
        steps.append(FomodStepOut(name=step.name, groups=groups))

    return FomodConfigOut(
        module_name=config.module_name,
        module_image=config.module_image,
        required_install_files=[
            FomodFileMapping(
                source=f.source,
                destination=f.destination,
                priority=f.priority,
                is_folder=f.is_folder,
            )
            for f in config.required_install_files
        ],
        steps=steps,
        has_conditional_installs=len(config.conditional_file_installs) > 0,
        total_steps=len(config.steps),
    )


@router.get("/config", response_model=FomodConfigOut)
def get_config(
    game_name: str,
    archive_filename: str,
    session: Session = Depends(get_session),
) -> FomodConfigOut:
    """Parse and return the FOMOD configuration for an archive."""
    config, _entries, _prefix, _game, _path = _get_fomod_config(
        game_name, archive_filename, session
    )
    return _config_to_out(config)


@router.post("/preview", response_model=FomodPreviewResult)
def preview_files(
    game_name: str,
    data: FomodPreviewRequest,
    session: Session = Depends(get_session),
) -> FomodPreviewResult:
    """Preview the files that would be installed with the given selections."""
    config, entries, prefix, _game, _path = _get_fomod_config(
        game_name, data.archive_filename, session
    )

    try:
        selections = {
            int(sk): {int(gk): v for gk, v in gv.items()} for sk, gv in data.selections.items()
        }
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, f"Invalid selection keys: {exc}") from exc

    resolved = compute_file_list(config, selections, entries, prefix)
    files = [
        FomodPreviewFile(
            game_relative_path=rf.game_relative_path,
            source=rf.archive_path,
            priority=rf.priority,
        )
        for rf in resolved
    ]
    return FomodPreviewResult(files=files, total_files=len(files))


@router.post("/install", response_model=InstallResult, status_code=201)
def install(
    game_name: str,
    data: FomodInstallRequest,
    session: Session = Depends(get_session),
) -> InstallResult:
    """Install a FOMOD archive with the given selections."""
    config, entries, prefix, game, archive_path = _get_fomod_config(
        game_name, data.archive_filename, session
    )

    try:
        selections = {
            int(sk): {int(gk): v for gk, v in gv.items()} for sk, gv in data.selections.items()
        }
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, f"Invalid selection keys: {exc}") from exc

    resolved = compute_file_list(config, selections, entries, prefix)

    # Extract nexus_mod_id from archive metadata
    nexus_mod_id: int | None = None
    try:
        metadata = inspect_archive(archive_path)
        if metadata and metadata.nexus_mod_id:
            nexus_mod_id = metadata.nexus_mod_id
    except (FileNotFoundError, ValueError, OSError):
        logger.debug("Could not extract nexus_mod_id from archive", exc_info=True)

    try:
        result = install_fomod(game, archive_path, session, resolved, data.mod_name, nexus_mod_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    return result
