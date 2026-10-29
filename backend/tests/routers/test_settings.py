import pytest


class TestListSettings:
    def test_empty(self, client):
        r = client.get("/api/v1/settings/")
        assert r.status_code == 200
        assert r.json() == []

    def test_masks_sensitive_keys(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"nexus_api_key": "secret123"}},
        )
        r = client.get("/api/v1/settings/")
        settings = r.json()
        nexus = next(s for s in settings if s["key"] == "nexus_api_key")
        assert nexus["value"] == "secr*t123"
        assert "secret123" not in nexus["value"]

    def test_shows_non_sensitive(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"save_backup_enabled": "false"}},
        )
        r = client.get("/api/v1/settings/")
        settings = r.json()
        enabled = next(s for s in settings if s["key"] == "save_backup_enabled")
        assert enabled["value"] == "false"


class TestUpdateSettings:
    def test_creates(self, client):
        r = client.put(
            "/api/v1/settings/",
            json={"settings": {"save_backup_enabled": "true"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data[0]["key"] == "save_backup_enabled"
        assert data[0]["value"] == "true"

    def test_updates_existing(self, client):
        client.put("/api/v1/settings/", json={"settings": {"save_backup_enabled": "true"}})
        client.put("/api/v1/settings/", json={"settings": {"save_backup_enabled": "false"}})
        r = client.get("/api/v1/settings/")
        val = next(s for s in r.json() if s["key"] == "save_backup_enabled")
        assert val["value"] == "false"

    @pytest.mark.parametrize(
        "payload",
        [
            {"save_backup_path": "C:/Windows"},
            {"theme": "dark"},
            {"save_backup_enabled": "maybe"},
            # One bad key rejects the whole request, valid keys included.
            {"save_backup_enabled": "false", "save_backup_path": "/tmp"},
        ],
    )
    def test_rejects_keys_outside_allowlist(self, client, payload):
        r = client.put("/api/v1/settings/", json={"settings": payload})
        assert r.status_code == 422
        assert client.get("/api/v1/settings/").json() == []

    def test_allowlist_matches_plan(self):
        from rippermod_manager.routers.settings import ALLOWED_SETTING_KEYS

        assert frozenset({"nexus_api_key", "save_backup_enabled"}) == ALLOWED_SETTING_KEYS

    def test_masks_in_response(self, client):
        r = client.put(
            "/api/v1/settings/",
            json={"settings": {"nexus_api_key": "nk-test123"}},
        )
        data = r.json()
        assert data[0]["value"] == "nk-t**t123"
        assert "nk-test123" not in data[0]["value"]


class TestSpecs:
    def test_specs_null(self, client):
        r = client.get("/api/v1/settings/specs")
        assert r.status_code == 200
        assert r.json() is None

    def test_specs_capture(self, client):
        payload = {
            "cpu": "i9-13900K",
            "gpu": "RTX 4090",
            "ram_gb": 64,
            "vram_gb": 24,
            "storage_type": "NVMe SSD",
            "os_version": "Windows 11",
            "resolution": "3440x1440",
        }
        r = client.post("/api/v1/settings/specs/capture", json=payload)
        assert r.status_code == 200
        assert r.json()["cpu"] == "i9-13900K"
