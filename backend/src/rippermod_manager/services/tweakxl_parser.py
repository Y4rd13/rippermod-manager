"""Parsers for TweakXL .yaml/.yml/.xl and .tweak file formats.

Converts raw file bytes into structured TweakEntry operations (set, append, remove)
without any database or filesystem interaction.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

from rippermod_manager.schemas.tweakxl import TweakEntry, TweakOperation

logger = logging.getLogger(__name__)

_UTF8_BOM = b"\xef\xbb\xbf"

_TWEAK_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*([+\-]?=)\s*(.+?)\s*$")

_OP_MAP: dict[str, TweakOperation] = {
    "=": TweakOperation.SET,
    "+=": TweakOperation.APPEND,
    "-=": TweakOperation.REMOVE,
}


# ---------------------------------------------------------------------------
# YAML tag sentinels
# ---------------------------------------------------------------------------


class _AppendMarker:
    """Sentinel for !append YAML tag."""

    __slots__ = ("value",)

    def __init__(self, value: object) -> None:
        self.value = value


class _RemoveMarker:
    """Sentinel for !remove YAML tag."""

    __slots__ = ("value",)

    def __init__(self, value: object) -> None:
        self.value = value


class _TweakXLLoader(yaml.SafeLoader):
    """YAML loader with TweakXL custom tag support."""


def _append_constructor(loader: yaml.Loader, node: yaml.Node) -> _AppendMarker:
    return _AppendMarker(loader.construct_scalar(node))  # type: ignore[arg-type]


def _remove_constructor(loader: yaml.Loader, node: yaml.Node) -> _RemoveMarker:
    return _RemoveMarker(loader.construct_scalar(node))  # type: ignore[arg-type]


_TweakXLLoader.add_constructor("!append", _append_constructor)
_TweakXLLoader.add_constructor("!append-once", _append_constructor)
_TweakXLLoader.add_constructor("!remove", _remove_constructor)


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------


def _normalize_value(value: object) -> str:
    """Convert any parsed value to a stable string for comparison."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return repr(value)


# ---------------------------------------------------------------------------
# YAML parser
# ---------------------------------------------------------------------------


def _flatten_yaml(
    prefix: str,
    data: Any,
) -> list[tuple[str, TweakOperation, str]]:
    """Recursively flatten a parsed YAML structure into (key, op, value) triples."""
    results: list[tuple[str, TweakOperation, str]] = []

    if isinstance(data, dict):
        for field, val in data.items():
            child_key = f"{prefix}.{field}" if prefix else str(field)
            results.extend(_flatten_yaml(child_key, val))

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, _AppendMarker):
                results.append((prefix, TweakOperation.APPEND, _normalize_value(item.value)))
            elif isinstance(item, _RemoveMarker):
                results.append((prefix, TweakOperation.REMOVE, _normalize_value(item.value)))
            else:
                results.append((prefix, TweakOperation.APPEND, _normalize_value(item)))

    else:
        results.append((prefix, TweakOperation.SET, _normalize_value(data)))

    return results


def parse_yaml_tweaks(
    content: bytes,
    source_file: str,
    mod_id: str,
) -> list[TweakEntry]:
    """Parse a TweakXL YAML file into a list of TweakEntry operations."""
    if not content or not content.strip():
        return []

    raw = content.lstrip(_UTF8_BOM)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    entries: list[TweakEntry] = []
    try:
        docs = list(yaml.load_all(text, Loader=_TweakXLLoader))
    except yaml.YAMLError:
        logger.warning("Failed to parse YAML file %s", source_file, exc_info=True)
        return []

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        for top_key, top_val in doc.items():
            for key, op, val in _flatten_yaml(str(top_key), top_val):
                entries.append(
                    TweakEntry(
                        key=key,
                        operation=op,
                        value=val,
                        source_file=source_file,
                        mod_id=mod_id,
                    )
                )
    return entries


# ---------------------------------------------------------------------------
# .tweak parser
# ---------------------------------------------------------------------------


def parse_tweak_file(
    content: bytes,
    source_file: str,
    mod_id: str,
) -> list[TweakEntry]:
    """Parse a TweakXL .tweak file into a list of TweakEntry operations."""
    if not content or not content.strip():
        return []

    raw = content.lstrip(_UTF8_BOM)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    entries: list[TweakEntry] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        m = _TWEAK_LINE_RE.match(stripped)
        if not m:
            continue
        key, operator, value = m.group(1), m.group(2), m.group(3)
        entries.append(
            TweakEntry(
                key=key,
                operation=_OP_MAP[operator],
                value=value,
                source_file=source_file,
                mod_id=mod_id,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_YAML_EXTENSIONS = {".yaml", ".yml", ".xl"}
_TWEAK_EXTENSIONS = {".tweak"}


def parse_tweak_bytes(
    content: bytes,
    source_file: str,
    mod_id: str,
) -> list[TweakEntry]:
    """Dispatch to the correct parser based on file extension."""
    lower = source_file.lower()
    dot_idx = lower.rfind(".")
    if dot_idx == -1:
        return []
    ext = lower[dot_idx:]
    if ext in _YAML_EXTENSIONS:
        return parse_yaml_tweaks(content, source_file, mod_id)
    if ext in _TWEAK_EXTENSIONS:
        return parse_tweak_file(content, source_file, mod_id)
    return []
