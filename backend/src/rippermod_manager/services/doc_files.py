"""Documentation files that ship in mod archives but are not game content."""

from __future__ import annotations

_DOC_SUFFIXES = (".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".url", ".html")
_DOC_PREFIXES = ("readme", "license", "changelog")


def is_doc_file(path: str) -> bool:
    """Whether an archive entry is documentation that installers do not place in the game."""
    name = path.rsplit("/", 1)[-1].lower()
    return name.endswith(_DOC_SUFFIXES) or name.startswith(_DOC_PREFIXES)


def is_root_doc_file(path: str) -> bool:
    """Whether ``path`` is a documentation file loose at the game root (no folder)."""
    normalised = path.replace("\\", "/").strip("/")
    return "/" not in normalised and is_doc_file(normalised)
