"""Tests for the per-game mods_dir resolver."""

from pathlib import Path

from rippermod_manager.models.game import Game
from rippermod_manager.services.paths import get_mods_dir, resolve_mods_dir


def test_resolve_mods_dir_default():
    """Without override, returns <install_path>/downloaded_mods."""
    result = resolve_mods_dir("/games/cyberpunk")
    assert result == Path("/games/cyberpunk/downloaded_mods")


def test_resolve_mods_dir_empty_string_uses_default():
    """Empty mods_dir string is treated as None."""
    result = resolve_mods_dir("/games/cyberpunk", mods_dir="")
    assert result == Path("/games/cyberpunk/downloaded_mods")


def test_resolve_mods_dir_override():
    """When mods_dir is set, return it verbatim."""
    result = resolve_mods_dir("/games/cyberpunk", mods_dir="/custom/staging")
    assert result == Path("/custom/staging")


def test_resolve_mods_dir_accepts_path_object():
    """Works with a Path install_path too."""
    result = resolve_mods_dir(Path("/games/cyberpunk"))
    assert result == Path("/games/cyberpunk/downloaded_mods")


def test_get_mods_dir_from_game_default():
    """A Game with no mods_dir gets the default."""
    game = Game(name="cp", domain_name="cyberpunk2077", install_path="/games/cp")
    assert get_mods_dir(game) == Path("/games/cp/downloaded_mods")


def test_get_mods_dir_from_game_override():
    """A Game with mods_dir set returns the override."""
    game = Game(
        name="cp",
        domain_name="cyberpunk2077",
        install_path="/games/cp",
        mods_dir="/custom/staging",
    )
    assert get_mods_dir(game) == Path("/custom/staging")
