from datetime import datetime

from rippermod_manager.models.install import DeployJournalEntry, InstalledMod, InstalledModFile


def test_installed_mod_has_vfs_fields():
    mod = InstalledMod(game_id=1, name="TestMod")
    assert mod.staging_dir == ""
    assert mod.deployed is False
    assert mod.deploy_drift is False


def test_installed_mod_file_has_link_metadata():
    f = InstalledModFile(installed_mod_id=1, relative_path="r6/scripts/foo.reds")
    assert f.source_path == ""
    assert f.link_kind == "hardlink"


def test_deploy_journal_entry_defaults():
    entry = DeployJournalEntry(
        game_id=1,
        operation="link",
        src="staging/mod/r6/scripts/foo.reds",
        dst="r6/scripts/foo.reds",
    )
    assert entry.status == "pending"
    assert entry.error == ""
    assert isinstance(entry.created_at, datetime)
