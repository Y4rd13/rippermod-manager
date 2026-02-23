import contextlib
import logging
import os

import pefile

from rippermod_manager.constants import GAME_REGISTRY

logger = logging.getLogger(__name__)


def read_game_version(install_path: str, domain_name: str) -> str | None:
    """Read the game version from the PE executable header."""
    game_info = GAME_REGISTRY.get(domain_name)
    if not game_info:
        return None

    exe_path = os.path.join(install_path, game_info["exe_path"])
    if not os.path.isfile(exe_path):
        return None

    try:
        pe = pefile.PE(exe_path, fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )

        if not hasattr(pe, "VS_FIXEDFILEINFO"):
            return None

        info = pe.VS_FIXEDFILEINFO[0]
        ms = info.FileVersionMS
        ls = info.FileVersionLS
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        logger.warning("Failed to read PE version from %s", exe_path, exc_info=True)
        return None
    finally:
        with contextlib.suppress(Exception):
            pe.close()  # type: ignore[possibly-undefined]
