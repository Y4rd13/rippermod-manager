"""Router tests for /api/v1/nexus/sso endpoints."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from rippermod_manager.schemas.nexus import NexusKeyResult
from rippermod_manager.services import sso_service


@pytest.fixture
def patched_ws(monkeypatch):
    """Patch sso_service.websockets.connect so /sso/start succeeds without network."""
    handshake = json.dumps(
        {"success": True, "data": {"connection_token": "router-ct"}, "error": None}
    )
    api_key_msg = json.dumps(
        {"success": True, "data": {"api_key": "router-key"}, "error": None}
    )
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(side_effect=[handshake, api_key_msg, asyncio.TimeoutError()])
    connect_ctx = AsyncMock()
    connect_ctx.__aenter__ = AsyncMock(return_value=ws)
    connect_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "rippermod_manager.services.sso_service.websockets.connect",
        lambda url, **_kw: connect_ctx,
    )

    class _StubNexusClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def validate_key(self):
            return NexusKeyResult(
                valid=True,
                username="router-user",
                is_premium=False,
                error="",
            )

    monkeypatch.setattr("rippermod_manager.nexus.client.NexusClient", _StubNexusClient)
    sso_service._sessions.clear()
    yield
    sso_service._sessions.clear()


class TestSSORouter:
    def test_sso_start_returns_uuid_and_authorize_url_with_registered_slug(
        self, client, patched_ws, monkeypatch
    ):
        monkeypatch.delenv("NEXUS_SSO_SLUG", raising=False)

        response = client.post("/api/v1/nexus/sso/start")

        assert response.status_code == 200
        body = response.json()
        assert "uuid" in body
        assert body["authorize_url"].startswith("https://www.nexusmods.com/sso?id=")
        assert "&application=y4rd13-rippermodmanager" in body["authorize_url"]
        assert body["uuid"] in body["authorize_url"]

    def test_sso_poll_unknown_returns_404(self, client):
        sso_service._sessions.clear()
        response = client.get("/api/v1/nexus/sso/poll/does-not-exist")
        assert response.status_code == 404

    def test_sso_poll_returns_session_status(self, client, patched_ws):
        start = client.post("/api/v1/nexus/sso/start").json()
        response = client.get(f"/api/v1/nexus/sso/poll/{start['uuid']}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"pending", "success", "error", "expired"}

    def test_sso_cancel_removes_session(self, client, patched_ws):
        start = client.post("/api/v1/nexus/sso/start").json()
        response = client.delete(f"/api/v1/nexus/sso/{start['uuid']}")
        assert response.status_code == 200
        assert response.json() == {"cancelled": True}

        poll = client.get(f"/api/v1/nexus/sso/poll/{start['uuid']}")
        assert poll.status_code == 404

    def test_sso_cancel_unknown_returns_404(self, client):
        sso_service._sessions.clear()
        response = client.delete("/api/v1/nexus/sso/missing")
        assert response.status_code == 404
