from rippermod_manager.models.install import InstalledMod


def test_installed_mod_has_vfs_fields():
    mod = InstalledMod(game_id=1, name="TestMod")
    assert mod.staging_dir == ""
    assert mod.deployed is False
    assert mod.deploy_drift is False
