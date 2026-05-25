import os
from typing import TypedDict

CYBERPUNK_DEFAULT_PATHS = [
    ("archive/pc/mod", "Main mod archives", True),
    ("archive/pc/patch", "Priority mod archives", True),
    ("bin/x64/plugins/cyber_engine_tweaks/mods", "CET script mods", True),
    ("red4ext/plugins", "RED4ext plugins", True),
    ("r6/scripts", "Redscript mods", True),
    ("r6/tweaks", "TweakXL tweaks", True),
    ("r6/config", "Mod config", True),
    ("bin/x64/plugins", "ASI/plugin loaders", True),
    ("mods", "REDmod mods", True),
    ("engine", "Engine config tweaks", True),
]
# bin/x64 is deliberately NOT a scan root: ~60 version-volatile vanilla DLLs
# (PhysX, DLSS/FSR, ICU, curl, ...) live loose there, and a denylist for them
# would be unmaintainable. Loose ASI mods are covered by bin/x64/plugins.

# Vanilla Cyberpunk 2077 files that live under scanned roots but must never be
# detected or adopted as mods. Lowercased, forward-slashed, install-relative.
# r6/config holds a small, stable set of vanilla input/UI config; mod content
# there (e.g. cybercmd/) is intentionally NOT listed so it stays detectable.
CYBERPUNK_VANILLA_DENYLIST = {
    "r6/config/inputcontexts.xml",
    "r6/config/inputdeadzones.xml",
    "r6/config/inputusermappings.xml",
    "r6/config/uiinputactions.xml",
    "r6/config/bumperssettings.json",
}

# Vanilla subtrees (prefix match) under scanned roots.
CYBERPUNK_VANILLA_PREFIXES = ("r6/config/settings/",)


def is_vanilla_path(rel_path: str) -> bool:
    """True if a game-relative path is a known vanilla file/subtree to skip in detection."""
    norm = rel_path.replace("\\", "/").lower()
    if norm in CYBERPUNK_VANILLA_DENYLIST:
        return True
    return any(norm.startswith(prefix) for prefix in CYBERPUNK_VANILLA_PREFIXES)


class GameRegistryEntry(TypedDict):
    exe_path: str
    mod_paths: list[tuple[str, str, bool]]


GAME_REGISTRY: dict[str, GameRegistryEntry] = {
    "cyberpunk2077": {
        "exe_path": os.path.join("bin", "x64", "Cyberpunk2077.exe"),
        "mod_paths": CYBERPUNK_DEFAULT_PATHS,
    },
}


class FrameworkEntry(TypedDict):
    key: str
    display_name: str
    nexus_mod_id: int
    marker: str  # path under the install whose presence means "installed"
    version_kind: str  # "pe" = read version from the binary; "none" = no on-disk source


# Core Cyberpunk 2077 modding frameworks. Markers, version sources, and Nexus ids
# verified against a real install (pefile probe) + each mod's Nexus page (2026-05-22).
FRAMEWORKS: list[FrameworkEntry] = [
    {
        "key": "red4ext",
        "display_name": "RED4ext",
        "nexus_mod_id": 2380,
        "marker": "red4ext/RED4ext.dll",
        "version_kind": "pe",
    },
    {
        "key": "cet",
        "display_name": "Cyber Engine Tweaks",
        "nexus_mod_id": 107,
        "marker": "bin/x64/plugins/cyber_engine_tweaks.asi",
        "version_kind": "pe",
    },
    {
        "key": "redscript",
        "display_name": "redscript",
        "nexus_mod_id": 1511,
        "marker": "engine/tools/scc.exe",
        "version_kind": "none",
    },
    {
        "key": "archivexl",
        "display_name": "ArchiveXL",
        "nexus_mod_id": 4198,
        "marker": "red4ext/plugins/ArchiveXL/ArchiveXL.dll",
        "version_kind": "pe",
    },
    {
        "key": "tweakxl",
        "display_name": "TweakXL",
        "nexus_mod_id": 4197,
        "marker": "red4ext/plugins/TweakXL/TweakXL.dll",
        "version_kind": "pe",
    },
    {
        "key": "codeware",
        "display_name": "Codeware",
        "nexus_mod_id": 7780,
        "marker": "red4ext/plugins/Codeware/Codeware.dll",
        "version_kind": "pe",
    },
]
