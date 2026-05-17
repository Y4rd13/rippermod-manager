from pathlib import Path

from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.vfs.untracked import find_untracked_files


def test_finds_files_not_owned_by_any_mod(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    install = Path(game.install_path)
    (install / "r6" / "scripts").mkdir(parents=True)
    (install / "r6" / "scripts" / "owned.reds").write_text("// a")
    (install / "r6" / "scripts" / "rogue.reds").write_text("// b")

    mod = InstalledMod(game_id=game.id, name="Mod", staging_dir="Mod")
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="r6/scripts/owned.reds",
            source_path="r6/scripts/owned.reds",
        )
    )
    session.commit()

    result = find_untracked_files(game, session)
    rogues = set(result)
    assert "r6/scripts/rogue.reds" in rogues
    assert "r6/scripts/owned.reds" not in rogues


def test_find_untracked_returns_empty_when_dirs_missing(in_memory_session, sample_game):
    """No mod roots = no untracked files."""
    session = in_memory_session
    game = sample_game
    result = find_untracked_files(game, session)
    assert result == []
