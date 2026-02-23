class TestOnboardingStatus:
    def test_fresh_step_0(self, client):
        r = client.get("/api/v1/onboarding/status")
        assert r.status_code == 200
        data = r.json()
        assert data["current_step"] == 0
        assert data["completed"] is False

    def test_with_openai_only_still_step_0(self, client):
        """OpenAI key is optional and does not advance the onboarding step."""
        client.put(
            "/api/v1/settings/",
            json={"settings": {"openai_api_key": "sk-test"}},
        )
        r = client.get("/api/v1/onboarding/status")
        assert r.json()["current_step"] == 0
        assert r.json()["has_openai_key"] is True

    def test_with_nexus_step_2(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"openai_api_key": "sk-test", "nexus_api_key": "nk-test"}},
        )
        r = client.get("/api/v1/onboarding/status")
        assert r.json()["current_step"] == 2

    def test_with_game_step_3(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"openai_api_key": "sk-test", "nexus_api_key": "nk-test"}},
        )
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.get("/api/v1/onboarding/status")
        assert r.json()["current_step"] == 3

    def test_completed_step_4(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"openai_api_key": "sk", "nexus_api_key": "nk"}},
        )
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        client.post(
            "/api/v1/onboarding/complete",
            json={"openai_api_key": "", "nexus_api_key": ""},
        )
        r = client.get("/api/v1/onboarding/status")
        assert r.json()["current_step"] == 4
        assert r.json()["completed"] is True


class TestCompleteOnboarding:
    def test_stores_keys(self, client):
        r = client.post(
            "/api/v1/onboarding/complete",
            json={"openai_api_key": "sk-new", "nexus_api_key": "nk-new"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["completed"] is True
        assert data["has_openai_key"] is True
        assert data["has_nexus_key"] is True

    def test_returns_status(self, client):
        r = client.post(
            "/api/v1/onboarding/complete",
            json={},
        )
        assert r.status_code == 200
        assert "completed" in r.json()
