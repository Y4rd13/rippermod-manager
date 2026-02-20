"""Tier 0.5: FOMOD info.xml and REDmod info.json archive metadata parsing.

Inspects mod archives in downloaded_mods/ for structured metadata before any
API calls.  FOMOD info.xml can contain the exact Nexus mod ID, name, version,
and author.  REDmod info.json provides mod name and version for Cyberpunk 2077
REDmod packages.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

from chat_nexus_mod_manager.archive.handler import open_archive
from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.nexus import NexusDownload
from chat_nexus_mod_manager.services.install_service import list_available_archives
from chat_nexus_mod_manager.services.nexus_helpers import upsert_nexus_mod
from chat_nexus_mod_manager.services.progress import ProgressCallback, noop_progress

logger = logging.getLogger(__name__)

_NEXUS_MOD_ID_RE = re.compile(r"nexusmods\.com/\w+/mods/(\d+)")


@dataclass(frozen=True)
class ArchiveMetadata:
    mod_name: str | None
    nexus_mod_id: int | None
    version: str | None
    author: str | None
    source: str  # "fomod" or "redmod"


@dataclass
class FomodParseResult:
    archives_inspected: int
    fomod_found: int
    redmod_found: int
    nexus_ids_extracted: int
    correlations_created: int


def _parse_fomod_info_xml(xml_bytes: bytes) -> ArchiveMetadata | None:
    """Parse FOMOD info.xml and extract mod metadata."""
    try:
        # Handle BOM for UTF-16/UTF-8-BOM encoded files
        text = xml_bytes
        if text.startswith(b"\xff\xfe") or text.startswith(b"\xfe\xff"):
            text = xml_bytes.decode("utf-16").encode("utf-8")
        elif text.startswith(b"\xef\xbb\xbf"):
            text = xml_bytes[3:]

        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    def _get_text(tag: str) -> str | None:
        # Try direct child first, then search recursively
        el = root.find(tag)
        if el is None:
            el = root.find(f".//{tag}")
        if el is not None and el.text:
            return el.text.strip()
        return None

    mod_name = _get_text("Name")
    version = _get_text("Version")
    author = _get_text("Author")
    website = _get_text("Website")

    nexus_mod_id: int | None = None

    # Try <Id> element first
    id_text = _get_text("Id")
    if id_text:
        with contextlib.suppress(ValueError):
            nexus_mod_id = int(id_text)

    # Fall back to parsing <Website> URL
    if nexus_mod_id is None and website:
        m = _NEXUS_MOD_ID_RE.search(website)
        if m:
            nexus_mod_id = int(m.group(1))

    if not mod_name and nexus_mod_id is None:
        return None

    return ArchiveMetadata(
        mod_name=mod_name,
        nexus_mod_id=nexus_mod_id,
        version=version,
        author=author,
        source="fomod",
    )


def _parse_redmod_info_json(json_bytes: bytes) -> ArchiveMetadata | None:
    """Parse REDmod info.json and extract mod metadata."""
    try:
        data = json.loads(json_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    version = data.get("version")
    version = version.strip() or None if isinstance(version, str) else None

    return ArchiveMetadata(
        mod_name=name.strip(),
        nexus_mod_id=None,
        version=version,
        author=None,
        source="redmod",
    )


def inspect_archive(archive_path: Path) -> ArchiveMetadata | None:
    """Open an archive and search for FOMOD info.xml or REDmod info.json metadata."""
    with open_archive(archive_path) as archive:
        entries = archive.list_entries()

        fomod_entry = None
        redmod_entry = None
        best_fomod_depth = float("inf")
        best_redmod_depth = float("inf")

        for entry in entries:
            if entry.is_dir:
                continue
            lower = entry.filename.lower().replace("\\", "/")
            parts = lower.split("/")
            depth = len(parts)

            # FOMOD: path ending with fomod/info.xml
            if lower.endswith("fomod/info.xml") and depth < best_fomod_depth:
                fomod_entry = entry
                best_fomod_depth = depth

            # REDmod: info.json at depth <= 2 (e.g. "modname/info.json" or "info.json")
            if parts[-1] == "info.json" and depth <= 2 and depth < best_redmod_depth:
                redmod_entry = entry
                best_redmod_depth = depth

        # Prefer FOMOD over REDmod (richer data)
        if fomod_entry is not None:
            xml_bytes = archive.read_file(fomod_entry)
            result = _parse_fomod_info_xml(xml_bytes)
            if result is not None:
                return result

        if redmod_entry is not None:
            json_bytes = archive.read_file(redmod_entry)
            return _parse_redmod_info_json(json_bytes)

    return None


def parse_archive_metadata(
    game: Game,
    session: Session,
    on_progress: ProgressCallback = noop_progress,
) -> FomodParseResult:
    """Inspect all archives in downloaded_mods/ for FOMOD/REDmod metadata.

    For each archive with metadata:
    1. If nexus_mod_id found -> create NexusDownload + NexusModMeta (if not exists)
    2. If archive matches an InstalledMod with a ModGroup -> create ModNexusCorrelation
    3. If better display name found -> update ModGroup.display_name
    """
    archives = list_available_archives(game)

    result = FomodParseResult(
        archives_inspected=0,
        fomod_found=0,
        redmod_found=0,
        nexus_ids_extracted=0,
        correlations_created=0,
    )

    if not archives:
        on_progress("fomod", "No archives found", 84)
        return result

    on_progress("fomod", f"Inspecting {len(archives)} archives...", 83)

    for i, archive_path in enumerate(archives):
        result.archives_inspected += 1

        try:
            metadata = inspect_archive(archive_path)
        except Exception:
            logger.warning("Failed to inspect archive: %s", archive_path.name, exc_info=True)
            continue

        if metadata is None:
            continue

        if metadata.source == "fomod":
            result.fomod_found += 1
        else:
            result.redmod_found += 1

        # Upsert NexusDownload if we have a Nexus mod ID
        dl: NexusDownload | None = None
        if metadata.nexus_mod_id is not None:
            result.nexus_ids_extracted += 1
            info: dict = {"name": metadata.mod_name or ""}
            if metadata.version:
                info["version"] = metadata.version
            if metadata.author:
                info["author"] = metadata.author
            dl = upsert_nexus_mod(
                session,
                game.id,  # type: ignore[arg-type]
                game.domain_name,
                metadata.nexus_mod_id,
                info,
                file_name=archive_path.name,
            )
            session.flush()

        # Try to link archive -> InstalledMod -> ModGroup
        installed_mod = session.exec(
            select(InstalledMod).where(
                InstalledMod.game_id == game.id,
                InstalledMod.source_archive == archive_path.name,
            )
        ).first()

        if installed_mod and installed_mod.mod_group_id:
            # Create correlation if we have a NexusDownload
            if dl is not None:
                existing_corr = session.exec(
                    select(ModNexusCorrelation).where(
                        ModNexusCorrelation.mod_group_id == installed_mod.mod_group_id,
                        ModNexusCorrelation.nexus_download_id == dl.id,
                    )
                ).first()
                if not existing_corr:
                    session.add(
                        ModNexusCorrelation(
                            mod_group_id=installed_mod.mod_group_id,
                            nexus_download_id=dl.id,  # type: ignore[arg-type]
                            score=0.95,
                            method="fomod",
                            reasoning=f"FOMOD info.xml contained mod ID {metadata.nexus_mod_id}",
                        )
                    )
                    result.correlations_created += 1

            # Update display name if we have a better one from metadata
            if metadata.mod_name:
                from chat_nexus_mod_manager.models.mod import ModGroup

                group = session.get(ModGroup, installed_mod.mod_group_id)
                if group and _is_filename_derived(group.display_name):
                    group.display_name = metadata.mod_name

        if (i + 1) % 10 == 0 or i == len(archives) - 1:
            pct = 83 + int(2 * (i + 1) / len(archives))
            on_progress("fomod", f"Inspected {i + 1}/{len(archives)} archives", pct)

    session.commit()
    return result


def _is_filename_derived(name: str) -> bool:
    """Heuristic: detect names derived from filenames rather than human-authored."""
    indicators = ["-", "_", "  "]
    return any(ind in name for ind in indicators) or bool(re.search(r"\d+\.\d+", name))
