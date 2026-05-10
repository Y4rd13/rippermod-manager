"""Tests for the Nexus SSO service — covers slug, wire protocol, and lifecycle."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
import websockets

from rippermod_manager.schemas.nexus import NexusKeyResult
from rippermod_manager.services import sso_service


def _make_mock_ws(recv_payloads: list[str]) -> AsyncMock:
    """Build an AsyncMock that simulates a Nexus SSO WebSocket exchange.

    `recv_payloads` is consumed in order on each `await ws.recv()`. Once
    exhausted, further calls raise asyncio.TimeoutError to surface bugs that
    over-read the socket.
    """
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(side_effect=[*recv_payloads, asyncio.TimeoutError()])
    return ws


def _patch_websockets(monkeypatch, ws_mock: AsyncMock) -> None:
    """Patch `websockets.connect` so `async with` yields `ws_mock`."""
    connect_ctx = AsyncMock()
    connect_ctx.__aenter__ = AsyncMock(return_value=ws_mock)
    connect_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "rippermod_manager.services.sso_service.websockets.connect",
        lambda url, **_kw: connect_ctx,
    )


def _patch_validate_key(monkeypatch, result: NexusKeyResult) -> None:
    """Patch `NexusClient` so `validate_key()` returns `result` without HTTP."""

    class _StubClient:
        def __init__(self, *args, **kwargs):
            self._result = result

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def validate_key(self):
            return self._result

    monkeypatch.setattr("rippermod_manager.nexus.client.NexusClient", _StubClient)


class TestApplicationSlug:
    def test_default_slug_is_registered_app(self, monkeypatch):
        monkeypatch.delenv("NEXUS_SSO_SLUG", raising=False)
        assert sso_service._get_application_slug() == "y4rd13-rippermodmanager"

    def test_slug_respects_env_override(self, monkeypatch):
        monkeypatch.setenv("NEXUS_SSO_SLUG", "custom-test-slug")
        assert sso_service._get_application_slug() == "custom-test-slug"


class TestStartSSO:
    async def test_authorize_url_contains_registered_slug(self, monkeypatch):
        monkeypatch.delenv("NEXUS_SSO_SLUG", raising=False)
        handshake = json.dumps(
            {"success": True, "data": {"connection_token": "ct-123"}, "error": None}
        )
        ws = _make_mock_ws([handshake])
        _patch_websockets(monkeypatch, ws)
        sso_service._sessions.clear()

        session_uuid, authorize_url = await sso_service.start_sso()

        assert session_uuid in sso_service._sessions
        assert authorize_url == (
            f"https://www.nexusmods.com/sso?id={session_uuid}"
            "&application=y4rd13-rippermodmanager"
        )
        sso_service.cancel_sso(session_uuid)

    async def test_authorize_url_honours_env_override(self, monkeypatch):
        monkeypatch.setenv("NEXUS_SSO_SLUG", "dev-slug")
        handshake = json.dumps(
            {"success": True, "data": {"connection_token": "ct-456"}, "error": None}
        )
        ws = _make_mock_ws([handshake])
        _patch_websockets(monkeypatch, ws)
        sso_service._sessions.clear()

        session_uuid, authorize_url = await sso_service.start_sso()

        assert "&application=dev-slug" in authorize_url
        sso_service.cancel_sso(session_uuid)
