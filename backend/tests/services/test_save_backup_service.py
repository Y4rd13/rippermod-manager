"""Tests for the save game backup service."""

from types import SimpleNamespace

import pytest

from rippermod_manager.services import save_backup_service as svc
from rippermod_manager.services.settings_helpers import set_setting
from rippermod_manager.services.vfs.primitives import GameRunningError


def _write_save(save_dir, name="SavedGame0", content=b"savedata"):
    d = save_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "sav.dat").write_bytes(content)
    (d / "metadata.9.dat").write_bytes(b"meta")
    return d


@pytest.fixture
def save_env(session, tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(svc.settings, "data_dir", data_dir)
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    set_setting(session, svc.PATH_KEY, str(save_dir))
    session.commit()
    return SimpleNamespace(session=session, save_dir=save_dir, data_dir=data_dir)


class TestSettings:
    def test_enabled_default_true(self, session):
        assert svc.is_enabled(session) is True

    def test_disabled_when_false(self, session):
        set_setting(session, svc.ENABLED_KEY, "false")
        session.commit()
        assert svc.is_enabled(session) is False

    def test_resolve_uses_override(self, save_env):
        assert svc.resolve_save_dir(save_env.session) == save_env.save_dir


class TestCreateAndList:
    def test_create_then_list(self, save_env):
        _write_save(save_env.save_dir)
        info = svc.create_backup(save_env.session, reason="manual", force=True)
        assert info is not None
        assert info["file_count"] == 2
        assert info["reason"] == "manual"

        backups = svc.list_backups(save_env.session)
        assert len(backups) == 1
        assert backups[0]["id"] == info["id"]

        backup_root = save_env.data_dir / "save_backups" / info["id"] / "saves"
        assert (backup_root / "SavedGame0" / "sav.dat").read_bytes() == b"savedata"

    def test_skip_when_no_save_dir(self, save_env):
        set_setting(save_env.session, svc.PATH_KEY, str(save_env.save_dir / "nope"))
        save_env.session.commit()
        assert svc.create_backup(save_env.session, reason="manual", force=True) is None


class TestDedupe:
    def test_dedupe_skips_unchanged(self, save_env):
        _write_save(save_env.save_dir)
        assert svc.create_backup(save_env.session, reason="pre-deploy", force=False) is not None
        # unchanged saves → skipped
        assert svc.create_backup(save_env.session, reason="pre-deploy", force=False) is None
        # force overrides dedupe
        assert svc.create_backup(save_env.session, reason="manual", force=True) is not None
        assert len(svc.list_backups(save_env.session)) == 2

    def test_change_triggers_new_backup(self, save_env):
        _write_save(save_env.save_dir)
        svc.create_backup(save_env.session, reason="pre-deploy", force=False)
        _write_save(save_env.save_dir, name="SavedGame1", content=b"new")
        assert svc.create_backup(save_env.session, reason="pre-deploy", force=False) is not None
        assert len(svc.list_backups(save_env.session)) == 2


class TestRetention:
    def test_keeps_only_max(self, save_env, monkeypatch):
        monkeypatch.setattr(svc, "MAX_BACKUPS", 3)
        _write_save(save_env.save_dir)
        for i in range(5):
            (save_env.save_dir / "SavedGame0" / "sav.dat").write_bytes(f"v{i}".encode())
            svc.create_backup(save_env.session, reason="manual", force=True)
        assert len(svc.list_backups(save_env.session)) == 3


class TestRestore:
    def test_restore_recovers_lost_save(self, save_env, monkeypatch):
        monkeypatch.setattr(
            "rippermod_manager.services.vfs.primitives.is_game_running", lambda *a, **k: False
        )
        _write_save(save_env.save_dir, content=b"original")
        info = svc.create_backup(save_env.session, reason="manual", force=True)
        (save_env.save_dir / "SavedGame0" / "sav.dat").write_bytes(b"corrupted")

        result = svc.restore_backup(save_env.session, info["id"])
        assert result["id"] == info["id"]
        assert (save_env.save_dir / "SavedGame0" / "sav.dat").read_bytes() == b"original"

    def test_restore_blocked_when_game_running(self, save_env, monkeypatch):
        monkeypatch.setattr(
            "rippermod_manager.services.vfs.primitives.is_game_running", lambda *a, **k: True
        )
        _write_save(save_env.save_dir)
        info = svc.create_backup(save_env.session, reason="manual", force=True)
        with pytest.raises(GameRunningError):
            svc.restore_backup(save_env.session, info["id"])

    def test_restore_rejects_traversal_id(self, save_env):
        with pytest.raises(ValueError):
            svc.restore_backup(save_env.session, "../../etc/passwd")

    def test_restore_missing_backup(self, save_env):
        with pytest.raises(FileNotFoundError):
            svc.restore_backup(save_env.session, "20200101-000000-000000")


class TestDeployHook:
    def test_backs_up_cyberpunk(self, save_env):
        _write_save(save_env.save_dir)
        svc.maybe_backup_for_deploy(SimpleNamespace(domain_name="cyberpunk2077"), save_env.session)
        assert len(svc.list_backups(save_env.session)) == 1

    def test_skips_non_cyberpunk(self, save_env):
        _write_save(save_env.save_dir)
        svc.maybe_backup_for_deploy(
            SimpleNamespace(domain_name="skyrimspecialedition"), save_env.session
        )
        assert svc.list_backups(save_env.session) == []

    def test_skips_when_disabled(self, save_env):
        set_setting(save_env.session, svc.ENABLED_KEY, "false")
        save_env.session.commit()
        _write_save(save_env.save_dir)
        svc.maybe_backup_for_deploy(SimpleNamespace(domain_name="cyberpunk2077"), save_env.session)
        assert svc.list_backups(save_env.session) == []

    def test_never_raises_on_failure(self, save_env, monkeypatch):
        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(svc, "create_backup", boom)
        # must not propagate — a backup failure can't abort a deploy
        svc.maybe_backup_for_deploy(SimpleNamespace(domain_name="cyberpunk2077"), save_env.session)
