"""Path resolution helpers for game-scoped directories.

The staging directory where mod archives live (`downloaded_mods/`) defaults to
`<install_path>/downloaded_mods/` but can be overridden per game via `Game.mods_dir`.
This module is the single source of truth — every caller should resolve through here.
"""

from pathlib import Path

from rippermod_manager.models.game import Game


def resolve_mods_dir(install_path: str | Path, mods_dir: str | None = None) -> Path:
    """Return the staging dir path, honoring an optional override.

    Args:
        install_path: The game's install path (always required as the default base).
        mods_dir: Optional override. If set, it is returned verbatim; otherwise
            ``<install_path>/downloaded_mods`` is used.
    """
    if mods_dir:
        return Path(mods_dir)
    return Path(install_path) / "downloaded_mods"


def get_mods_dir(game: Game) -> Path:
    """Return the staging dir for a Game, honoring its per-game override."""
    return resolve_mods_dir(game.install_path, game.mods_dir)
