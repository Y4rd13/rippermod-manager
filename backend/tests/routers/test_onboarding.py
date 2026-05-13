class TestOnboardingStatus:
    def test_fresh_step_0(self, client):
        r = client.get("/api/v1/onboarding/status")
        assert r.status_code == 200
        data = r.json()
        assert data["current_step"] == 0
        assert data["completed"] is False

    def test_with_nexus_step_1(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"nexus_api_key": "nk-test"}},
        )
        r = client.get("/api/v1/onboarding/status")
        assert r.json()["current_step"] == 1

    def test_with_game_step_2(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"nexus_api_key": "nk-test"}},
        )
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.get("/api/v1/onboarding/status")
        assert r.json()["current_step"] == 2

    def test_completed_step_3(self, client):
        client.put(
            "/api/v1/settings/",
            json={"settings": {"nexus_api_key": "nk"}},
        )
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        client.post(
            "/api/v1/onboarding/complete",
            json={},
        )
        r = client.get("/api/v1/onboarding/status")
        assert r.json()["current_step"] == 3
        assert r.json()["completed"] is True


class TestCompleteOnboarding:
    def test_marks_completed(self, client):
        r = client.post(
            "/api/v1/onboarding/complete",
            json={},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["completed"] is True

    def test_returns_status(self, client):
        r = client.post(
            "/api/v1/onboarding/complete",
            json={},
        )
        assert r.status_code == 200
        assert "completed" in r.json()
