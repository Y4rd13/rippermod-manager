"""Tests for the save backup endpoints."""

from types import SimpleNamespace

import pytest
from sqlmodel import Session

from rippermod_manager.services import save_backup_service as svc
from rippermod_manager.services.settings_helpers import set_setting


@pytest.fixture
def save_api(client, engine, tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(svc.settings, "data_dir", data_dir)
    save_dir = tmp_path / "saves" / "SavedGame0"
    save_dir.mkdir(parents=True)
    (save_dir / "sav.dat").write_bytes(b"x")
    with Session(engine) as s:
        set_setting(s, svc.PATH_KEY, str(tmp_path / "saves"))
        s.commit()
    return SimpleNamespace(client=client, save_dir=tmp_path / "saves", data_dir=data_dir)


class TestSaveBackupRouter:
    def test_status_empty(self, save_api):
        resp = save_api.client.get("/api/v1/save-backups/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["save_dir_exists"] is True
        assert data["backups"] == []

    def test_backup_now_then_listed(self, save_api):
        resp = save_api.client.post("/api/v1/save-backups/backup-now")
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] is True
        assert body["backup"]["file_count"] == 1

        listed = save_api.client.get("/api/v1/save-backups/").json()
        assert len(listed["backups"]) == 1
        assert listed["backups"][0]["id"] == body["backup"]["id"]

    def test_backup_now_no_save_dir_409(self, save_api, engine):
        with Session(engine) as s:
            set_setting(s, svc.PATH_KEY, str(save_api.save_dir / "missing"))
            s.commit()
        resp = save_api.client.post("/api/v1/save-backups/backup-now")
        assert resp.status_code == 409

    def test_restore_invalid_id_400(self, save_api):
        resp = save_api.client.post("/api/v1/save-backups/restore", json={"id": "../bad"})
        assert resp.status_code == 400

    def test_restore_roundtrip(self, save_api, monkeypatch):
        monkeypatch.setattr(
            "rippermod_manager.services.vfs.primitives.is_game_running", lambda *a, **k: False
        )
        created = save_api.client.post("/api/v1/save-backups/backup-now").json()
        backup_id = created["backup"]["id"]
        (save_api.save_dir / "SavedGame0" / "sav.dat").write_bytes(b"corrupt")

        resp = save_api.client.post("/api/v1/save-backups/restore", json={"id": backup_id})
        assert resp.status_code == 200
        assert resp.json()["restored"] is True
        assert (save_api.save_dir / "SavedGame0" / "sav.dat").read_bytes() == b"x"


class TestSetSaveBackupPath:
    def _put(self, save_api, path):
        return save_api.client.put("/api/v1/save-backups/path", json={"path": path})

    def test_folder_with_save_subfolder_is_accepted(self, save_api):
        resp = self._put(save_api, str(save_api.save_dir))
        assert resp.status_code == 200
        assert resp.json()["save_dir"] == str(save_api.save_dir)
        assert resp.json()["save_dir_exists"] is True

    @pytest.mark.parametrize("path", [r"\\server\share\saves", "//server/share"])
    def test_unc_is_rejected(self, save_api, path):
        assert self._put(save_api, path).status_code == 422

    def test_missing_folder_is_rejected(self, save_api):
        assert self._put(save_api, str(save_api.save_dir / "missing")).status_code == 422

    def test_relative_folder_is_rejected(self, save_api):
        assert self._put(save_api, "saves").status_code == 422

    def test_folder_without_sav_dat_is_rejected(self, save_api, tmp_path):
        other = tmp_path / "Windows" / "System32"
        (other / "drivers").mkdir(parents=True)
        resp = self._put(save_api, str(other))
        assert resp.status_code == 422
        status = save_api.client.get("/api/v1/save-backups/").json()
        assert status["save_dir"] == str(save_api.save_dir)

    def test_default_folder_without_saves_is_accepted(self, save_api, tmp_path, monkeypatch):
        default = tmp_path / "home" / "Saved Games" / "CD Projekt Red" / "Cyberpunk 2077"
        default.mkdir(parents=True)
        monkeypatch.setattr(svc, "default_save_dir", lambda: default)
        assert self._put(save_api, str(default)).status_code == 200

    def test_empty_path_resets_to_default(self, save_api, tmp_path, monkeypatch):
        default = tmp_path / "default-saves"
        monkeypatch.setattr(svc, "default_save_dir", lambda: default)
        resp = self._put(save_api, "")
        assert resp.status_code == 200
        assert resp.json()["save_dir"] == str(default)
