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
        assert nexus["value"] == "***"

    def test_shows_non_sensitive(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"theme": "dark"}},
        )
        r = client.get("/api/v1/settings/")
        settings = r.json()
        theme = next(s for s in settings if s["key"] == "theme")
        assert theme["value"] == "dark"


class TestUpdateSettings:
    def test_creates(self, client):
        r = client.put(
            "/api/v1/settings/",
            json={"settings": {"new_key": "new_val"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data[0]["key"] == "new_key"
        assert data[0]["value"] == "new_val"

    def test_updates_existing(self, client):
        client.put("/api/v1/settings/", json={"settings": {"k": "v1"}})
        client.put("/api/v1/settings/", json={"settings": {"k": "v2"}})
        r = client.get("/api/v1/settings/")
        val = next(s for s in r.json() if s["key"] == "k")
        assert val["value"] == "v2"

    def test_masks_in_response(self, client):
        r = client.put(
            "/api/v1/settings/",
            json={"settings": {"openai_api_key": "sk-test123"}},
        )
        data = r.json()
        assert data[0]["value"] == "***"


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
