"""The Nexus edition no longer downloads its own installer (S12)."""


def test_app_update_download_endpoint_is_gone(client):
    assert client.get("/api/v1/app-update/download").status_code == 404
    assert client.post("/api/v1/app-update/download").status_code == 404
    assert client.post("/api/v1/app-update/download/cancel").status_code == 404
