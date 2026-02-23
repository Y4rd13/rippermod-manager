"""Shared normalization utilities for mod name matching."""

import re

SEPARATOR_RE = re.compile(r"[_\-.\s]+")
CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
ORDER_PREFIX_RE = re.compile(r"^#+|^z(?=[A-Z])")

# Words that should stay uppercase in display names
_ACRONYMS = frozenset(
    {
        "CET",
        "XL",
        "HD",
        "UI",
        "AI",
        "NPC",
        "FX",
        "HQ",
        "VFX",
        "SFX",
        "RPG",
        "DLC",
        "XML",
        "API",
    }
)


def split_camel(name: str) -> str:
    """Insert spaces at CamelCase boundaries.

    >>> split_camel("EgghancedBloodFx")
    'Egghanced Blood Fx'
    >>> split_camel("CETMod")
    'CET Mod'
    """
    return CAMEL_RE.sub(" ", name)


def strip_ordering_prefix(name: str) -> str:
    """Remove Cyberpunk load-order prefixes (## and z before uppercase).

    >>> strip_ordering_prefix("##EgghancedBloodFx")
    'EgghancedBloodFx'
    >>> strip_ordering_prefix("zModName")
    'ModName'
    >>> strip_ordering_prefix("zebra")
    'zebra'
    """
    return ORDER_PREFIX_RE.sub("", name)


def clean_display_name(raw: str) -> str:
    """Produce a human-friendly display name: strip prefix, split camel, smart title-case.

    >>> clean_display_name("##EgghancedBloodFx")
    'Egghanced Blood Fx'
    >>> clean_display_name("##########VendorsXL")
    'Vendors XL'
    """
    name = strip_ordering_prefix(raw)
    name = split_camel(name)
    words = SEPARATOR_RE.split(name)
    result: list[str] = []
    for w in words:
        if not w:
            continue
        if w.upper() in _ACRONYMS:
            result.append(w.upper())
        else:
            result.append(w[0].upper() + w[1:] if len(w) > 1 else w.upper())
    return " ".join(result)
