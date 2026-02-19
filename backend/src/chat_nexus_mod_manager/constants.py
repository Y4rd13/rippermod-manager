import os
from typing import TypedDict

CYBERPUNK_DEFAULT_PATHS = [
    ("archive/pc/mod", "Main mod archives", True),
    ("bin/x64/plugins/cyber_engine_tweaks/mods", "CET script mods", True),
    ("red4ext/plugins", "RED4ext plugins", True),
    ("r6/scripts", "Redscript mods", True),
    ("r6/tweaks", "TweakXL tweaks", True),
    ("bin/x64/plugins", "ASI/plugin loaders", True),
    ("mods", "REDmod mods", True),
]


class GameRegistryEntry(TypedDict):
    exe_path: str
    mod_paths: list[tuple[str, str, bool]]


GAME_REGISTRY: dict[str, GameRegistryEntry] = {
    "cyberpunk2077": {
        "exe_path": os.path.join("bin", "x64", "Cyberpunk2077.exe"),
        "mod_paths": CYBERPUNK_DEFAULT_PATHS,
    },
}
