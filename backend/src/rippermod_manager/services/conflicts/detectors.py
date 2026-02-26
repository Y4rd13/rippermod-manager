"""Conflict detector protocol, registry, and built-in detectors.

Each detector scans all installed mods for a specific kind of conflict and
returns a list of ``ConflictEvidence`` rows ready for persistence.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Protocol

from sqlmodel import Session

from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind, Severity
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol + Registry
# ---------------------------------------------------------------------------


class ConflictDetector(Protocol):
    """Interface that all conflict detectors must satisfy."""

    kind: ConflictKind

    def detect(
        self,
        game: Game,
        installed_mods: list[InstalledMod],
        session: Session,
    ) -> list[ConflictEvidence]: ...


_DETECTORS: list[type[ConflictDetector]] = []


def register_detector(cls: type[ConflictDetector]) -> type[ConflictDetector]:
    """Class decorator that adds a detector to the global registry."""
    if cls not in _DETECTORS:
        _DETECTORS.append(cls)
    return cls


def get_all_detectors() -> list[ConflictDetector]:
    """Instantiate and return all registered detectors."""
    return [cls() for cls in _DETECTORS]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

_HIGH_SEVERITY_PREFIXES = ("archive/pc/mod", "bin/x64/plugins")
_MEDIUM_SEVERITY_PREFIXES = ("r6/scripts", "r6/tweaks", "mods")


def _archive_entry_severity(path: str) -> Severity:
    """Determine severity for a file-path conflict based on path prefix."""
    lower = path.lower()
    for prefix in _HIGH_SEVERITY_PREFIXES:
        if lower.startswith(prefix):
            return Severity.high
    for prefix in _MEDIUM_SEVERITY_PREFIXES:
        if lower.startswith(prefix):
            return Severity.medium
    return Severity.low


# ---------------------------------------------------------------------------
# Built-in detectors
# ---------------------------------------------------------------------------


@register_detector
class ArchiveEntryDetector:
    """Detects file-path collisions across all installed (enabled) mods."""

    kind = ConflictKind.archive_entry

    def detect(
        self,
        game: Game,
        installed_mods: list[InstalledMod],
        session: Session,
    ) -> list[ConflictEvidence]:
        path_owners: dict[str, list[int]] = {}
        for mod in installed_mods:
            if mod.disabled:
                continue
            for f in mod.files:
                normalised = f.relative_path.replace("\\", "/").lower()
                path_owners.setdefault(normalised, []).append(mod.id)  # type: ignore[arg-type]

        evidence: list[ConflictEvidence] = []
        for path, mod_ids in path_owners.items():
            if len(mod_ids) < 2:
                continue
            evidence.append(
                ConflictEvidence(
                    game_id=game.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=_archive_entry_severity(path),
                    key=path,
                    mod_ids=",".join(str(m) for m in mod_ids),
                    winner_mod_id=mod_ids[-1],
                    detail=json.dumps({"count": len(mod_ids)}),
                )
            )
        return evidence


# Redscript annotation patterns
_WRAP_RE = re.compile(r"@wrapMethod\s*\(\s*(\w+)\s*\)", re.IGNORECASE)
_REPLACE_RE = re.compile(r"@replaceMethod\s*\(\s*(\w+)\s*\)", re.IGNORECASE)
_ADD_METHOD_RE = re.compile(r"@addMethod\s*\(\s*(\w+)\s*\)", re.IGNORECASE)
_ADD_FIELD_RE = re.compile(r"@addField\s*\(\s*(\w+)\s*\)", re.IGNORECASE)
_FUNC_RE = re.compile(r"(?:public|private|protected)?\s*(?:static\s+)?(?:func|cb\s+func)\s+(\w+)")


@register_detector
class RedscriptTargetDetector:
    """Detects redscript mods that wrap/replace the same method."""

    kind = ConflictKind.redscript_target

    def detect(
        self,
        game: Game,
        installed_mods: list[InstalledMod],
        session: Session,
    ) -> list[ConflictEvidence]:
        game_dir = Path(game.install_path)
        target_owners: dict[str, list[tuple[int, str]]] = {}

        for mod in installed_mods:
            if mod.disabled:
                continue
            for f in mod.files:
                if not f.relative_path.lower().endswith(".reds"):
                    continue
                file_path = game_dir / f.relative_path
                if not file_path.exists():
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                self._parse_redscript(content, mod.id, target_owners)  # type: ignore[arg-type]

        evidence: list[ConflictEvidence] = []
        for key, owners in target_owners.items():
            mod_ids = list(dict.fromkeys(o[0] for o in owners))
            if len(mod_ids) < 2:
                continue
            ann_types = list(dict.fromkeys(o[1] for o in owners))
            has_replace_or_wrap = any(a in ("wrapMethod", "replaceMethod") for a in ann_types)
            severity = Severity.high if has_replace_or_wrap else Severity.medium
            evidence.append(
                ConflictEvidence(
                    game_id=game.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=severity,
                    key=key,
                    mod_ids=",".join(str(m) for m in mod_ids),
                    winner_mod_id=None,
                    detail=json.dumps({"annotations": ann_types}),
                )
            )
        return evidence

    @staticmethod
    def _parse_redscript(
        content: str,
        mod_id: int,
        target_owners: dict[str, list[tuple[int, str]]],
    ) -> None:
        """Extract annotation targets from redscript source."""
        lines = content.split("\n")
        patterns = [
            (_WRAP_RE, "wrapMethod"),
            (_REPLACE_RE, "replaceMethod"),
            (_ADD_METHOD_RE, "addMethod"),
            (_ADD_FIELD_RE, "addField"),
        ]
        for i, line in enumerate(lines):
            for pattern, ann_type in patterns:
                m = pattern.search(line)
                if not m:
                    continue
                class_name = m.group(1)
                func_name = "unknown"
                for j in range(i + 1, min(i + 10, len(lines))):
                    fm = _FUNC_RE.search(lines[j])
                    if fm:
                        func_name = fm.group(1)
                        break
                target_key = f"{class_name}.{func_name}"
                target_owners.setdefault(target_key, []).append((mod_id, ann_type))


# TweakDB key pattern: top-level YAML keys that look like TweakDB paths
_TWEAK_KEY_RE = re.compile(
    r"^([A-Z]\w+(?:\.\w+)+?)(\.\$append|\.\!append)?:",
    re.MULTILINE,
)
_TWEAK_EXTENSIONS = {".yaml", ".yml", ".tweak"}


@register_detector
class TweakKeyDetector:
    """Detects TweakXL/TweakDB key collisions across tweak files."""

    kind = ConflictKind.tweak_key

    def detect(
        self,
        game: Game,
        installed_mods: list[InstalledMod],
        session: Session,
    ) -> list[ConflictEvidence]:
        game_dir = Path(game.install_path)
        key_owners: dict[str, list[tuple[int, bool]]] = {}

        for mod in installed_mods:
            if mod.disabled:
                continue
            for f in mod.files:
                lower_path = f.relative_path.lower()
                if not any(lower_path.endswith(ext) for ext in _TWEAK_EXTENSIONS):
                    continue
                norm = lower_path.replace("\\", "/")
                if "r6/tweaks" not in norm:
                    continue
                file_path = game_dir / f.relative_path
                if not file_path.exists():
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for key, is_append in self._extract_tweak_keys(content):
                    key_owners.setdefault(key, []).append(
                        (mod.id, is_append)  # type: ignore[arg-type]
                    )

        evidence: list[ConflictEvidence] = []
        for key, owners in key_owners.items():
            mod_ids = list(dict.fromkeys(o[0] for o in owners))
            if len(mod_ids) < 2:
                continue
            all_append = all(o[1] for o in owners)
            severity = Severity.low if all_append else Severity.medium
            evidence.append(
                ConflictEvidence(
                    game_id=game.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=severity,
                    key=key,
                    mod_ids=",".join(str(m) for m in mod_ids),
                    winner_mod_id=None,
                    detail=json.dumps({"all_append": all_append}),
                )
            )
        return evidence

    @staticmethod
    def _extract_tweak_keys(content: str) -> list[tuple[str, bool]]:
        """Extract TweakDB flat keys from YAML-ish tweak content.

        Returns (key, is_append) tuples. TweakXL append syntax uses
        ``$append`` or ``!append`` suffixes.
        """
        results: list[tuple[str, bool]] = []
        for match in _TWEAK_KEY_RE.finditer(content):
            key = match.group(1)
            is_append = match.group(2) is not None
            results.append((key, is_append))
        return results
