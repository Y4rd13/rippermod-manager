import os
from pathlib import Path
from unittest.mock import patch

from sqlmodel import select

from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.vfs.migration import migrate_to_vfs


def test_migration_moves_files_to_staging_and_hardlinks(in_memory_session, sample_game):
    """Existing copy-installed mod migrates to staging + hardlinks."""
    session = in_memory_session
    game = sample_game
    install = Path(game.install_path)
    (install / "r6" / "scripts").mkdir(parents=True)
    (install / "r6" / "scripts" / "foo.reds").write_text("// pre-vfs")

    mod = InstalledMod(game_id=game.id, name="Legacy", staging_dir="", deployed=False)
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="r6/scripts/foo.reds",
            source_path="",
            link_kind="hardlink",
        )
    )
    session.commit()

    with patch("rippermod_manager.services.vfs.migration.is_game_running", return_value=False):
        report = migrate_to_vfs(game, session)

    assert report.migrated_mods == 1
    assert report.migrated_files == 1
    assert report.errors == []

    staging_file = install / "downloaded_mods" / "Legacy" / "r6" / "scripts" / "foo.reds"
    game_file = install / "r6" / "scripts" / "foo.reds"
    assert staging_file.exists(), "file should be in staging"
    assert game_file.exists(), "hardlink should remain at game-dir path"
    assert os.path.samefile(staging_file, game_file)
    assert staging_file.read_text() == "// pre-vfs"

    session.refresh(mod)
    assert mod.staging_dir == "Legacy"
    assert mod.deployed is True

    f = session.exec(
        select(InstalledModFile).where(InstalledModFile.installed_mod_id == mod.id)
    ).one()
    assert f.source_path == "r6/scripts/foo.reds"


def test_migration_refuses_if_game_running(in_memory_session, sample_game):
    """Pre-flight check rejects migration when game is running."""
    session = in_memory_session
    game = sample_game

    with patch("rippermod_manager.services.vfs.migration.is_game_running", return_value=True):
        report = migrate_to_vfs(game, session)

    assert report.migrated_mods == 0
    assert any("running" in e.lower() for e in report.errors)


def test_migration_skips_already_migrated(in_memory_session, sample_game):
    """Mods with non-empty staging_dir are not re-migrated."""
    session = in_memory_session
    game = sample_game

    mod = InstalledMod(game_id=game.id, name="Already", staging_dir="Already", deployed=True)
    session.add(mod)
    session.commit()

    with patch("rippermod_manager.services.vfs.migration.is_game_running", return_value=False):
        report = migrate_to_vfs(game, session)

    assert report.migrated_mods == 0
    assert report.errors == []
