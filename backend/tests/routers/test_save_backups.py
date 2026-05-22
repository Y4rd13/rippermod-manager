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
