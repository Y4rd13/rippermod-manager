from rippermod_manager.models.install import InstalledMod, InstalledModFile


def test_installed_mod_has_vfs_fields():
    mod = InstalledMod(game_id=1, name="TestMod")
    assert mod.staging_dir == ""
    assert mod.deployed is False
    assert mod.deploy_drift is False


def test_installed_mod_file_has_link_metadata():
    f = InstalledModFile(installed_mod_id=1, relative_path="r6/scripts/foo.reds")
    assert f.source_path == ""
    assert f.link_kind == "hardlink"
