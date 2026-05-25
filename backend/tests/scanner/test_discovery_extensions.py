from rippermod_manager.constants import CYBERPUNK_DEFAULT_PATHS, is_vanilla_path
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.scanner.service import INTERESTING_EXTENSIONS, _discover_files


def test_tweak_and_preset_are_interesting():
    # TweakXL mods frequently ship raw .tweak files; .preset for appearance mods.
    assert ".tweak" in INTERESTING_EXTENSIONS
    assert ".preset" in INTERESTING_EXTENSIONS


def test_archive_pc_patch_and_r6_config_are_default_roots():
    roots = {rel for rel, _label, _enabled in CYBERPUNK_DEFAULT_PATHS}
    assert "archive/pc/patch" in roots
    assert "r6/config" in roots


def test_bin_x64_is_not_a_blanket_root():
    # ~60 version-volatile vanilla DLLs live loose in bin/x64; deliberately not scanned.
    roots = {rel for rel, _label, _enabled in CYBERPUNK_DEFAULT_PATHS}
    assert "bin/x64" not in roots


def test_is_vanilla_path_matches_known_vanilla():
    assert is_vanilla_path("r6/config/inputUserMappings.xml") is True  # case-insensitive
    assert is_vanilla_path("r6/config/settings/anything.json") is True  # prefix subtree
    assert is_vanilla_path("r6/config/bumpersSettings.json") is True


def test_is_vanilla_path_allows_mod_content():
    assert is_vanilla_path("r6/config/cybercmd/cmd.json") is False
    assert is_vanilla_path("archive/pc/mod/CoolMod.archive") is False
    assert is_vanilla_path("r6/tweaks/MyTweak.tweak") is False


def test_discover_skips_vanilla_but_keeps_mod_files_in_r6_config(session, tmp_path):
    install = tmp_path / "game"
    (install / "r6" / "config").mkdir(parents=True)
    (install / "r6" / "config" / "inputUserMappings.xml").write_text("<vanilla/>")  # vanilla
    (install / "r6" / "config" / "cybercmd").mkdir()
    (install / "r6" / "config" / "cybercmd" / "mod.json").write_text("{}")  # mod content
    g = Game(name="CP", domain_name="cyberpunk2077", install_path=str(install))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="r6/config"))
    session.commit()
    session.refresh(g)
    _ = g.mod_paths

    discovered = {p.relative_to(install).as_posix() for p, _root in _discover_files(g)}
    assert "r6/config/cybercmd/mod.json" in discovered
    assert "r6/config/inputUserMappings.xml" not in discovered  # vanilla filtered out
