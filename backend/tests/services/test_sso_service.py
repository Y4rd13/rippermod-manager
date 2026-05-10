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
    ws.recv = AsyncMock(side_effect=[*recv_payloads, TimeoutError()])
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
            f"https://www.nexusmods.com/sso?id={session_uuid}&application=y4rd13-rippermodmanager"
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


class TestHandshakePayload:
    async def test_handshake_uses_protocol_2_with_no_extra_fields(self, monkeypatch):
        handshake = json.dumps(
            {"success": True, "data": {"connection_token": "ct-xyz"}, "error": None}
        )
        ws = _make_mock_ws([handshake])
        _patch_websockets(monkeypatch, ws)
        sso_service._sessions.clear()

        session_uuid, _ = await sso_service.start_sso()

        ws.send.assert_called_once()
        sent_payload = json.loads(ws.send.call_args.args[0])
        assert set(sent_payload.keys()) == {"id", "token", "protocol"}
        assert sent_payload["id"] == session_uuid
        assert sent_payload["token"] is None
        assert sent_payload["protocol"] == 2

        sso_service.cancel_sso(session_uuid)


class TestListenerSuccess:
    async def test_listener_completes_and_validates_api_key(self, monkeypatch):
        handshake = json.dumps(
            {"success": True, "data": {"connection_token": "ct-1"}, "error": None}
        )
        api_key_msg = json.dumps({"success": True, "data": {"api_key": "valid-key"}, "error": None})
        ws = _make_mock_ws([handshake, api_key_msg])
        _patch_websockets(monkeypatch, ws)
        _patch_validate_key(
            monkeypatch,
            NexusKeyResult(
                valid=True,
                username="testuser",
                is_premium=False,
                error="",
            ),
        )
        sso_service._sessions.clear()

        session_uuid, _ = await sso_service.start_sso()
        session = sso_service._sessions[session_uuid]

        await asyncio.wait_for(session.task, timeout=2.0)

        assert session.status == sso_service.SSOStatus.SUCCESS
        assert session.api_key == "valid-key"
        assert session.connection_token == "ct-1"
        assert session.result is not None
        assert session.result.username == "testuser"
        assert session.error == ""

        sso_service._sessions.clear()


class TestListenerErrors:
    async def test_listener_handshake_rejection_sets_error(self, monkeypatch):
        handshake = json.dumps({"success": False, "data": {}, "error": "invalid id"})
        ws = _make_mock_ws([handshake])
        _patch_websockets(monkeypatch, ws)
        sso_service._sessions.clear()

        with pytest.raises(RuntimeError, match="invalid id"):
            await sso_service.start_sso()

    async def test_listener_validation_failure_propagates(self, monkeypatch):
        handshake = json.dumps(
            {"success": True, "data": {"connection_token": "ct-2"}, "error": None}
        )
        api_key_msg = json.dumps({"success": True, "data": {"api_key": "bad-key"}, "error": None})
        ws = _make_mock_ws([handshake, api_key_msg])
        _patch_websockets(monkeypatch, ws)
        _patch_validate_key(
            monkeypatch,
            NexusKeyResult(valid=False, username="", is_premium=False, error="unauthorized"),
        )
        sso_service._sessions.clear()

        with pytest.raises(RuntimeError, match="unauthorized"):
            await sso_service.start_sso()

    async def test_listener_connection_closed_sets_error(self, monkeypatch):
        ws = AsyncMock()
        ws.send = AsyncMock(
            side_effect=websockets.exceptions.ConnectionClosed(rcvd=None, sent=None)
        )
        ws.recv = AsyncMock()
        connect_ctx = AsyncMock()
        connect_ctx.__aenter__ = AsyncMock(return_value=ws)
        connect_ctx.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(
            "rippermod_manager.services.sso_service.websockets.connect",
            lambda url, **_kw: connect_ctx,
        )
        sso_service._sessions.clear()

        with pytest.raises(RuntimeError, match="WebSocket connection closed"):
            await sso_service.start_sso()


class TestSessionLifecycle:
    def test_poll_returns_none_for_unknown_uuid(self):
        sso_service._sessions.clear()
        assert sso_service.poll_sso("nonexistent") is None

    async def test_poll_returns_active_session(self, monkeypatch):
        handshake = json.dumps(
            {"success": True, "data": {"connection_token": "ct-3"}, "error": None}
        )
        ws = _make_mock_ws([handshake])
        _patch_websockets(monkeypatch, ws)
        sso_service._sessions.clear()

        session_uuid, _ = await sso_service.start_sso()
        polled = sso_service.poll_sso(session_uuid)

        assert polled is not None
        assert polled.uuid == session_uuid
        sso_service.cancel_sso(session_uuid)

    async def test_cancel_removes_session_and_cancels_task(self, monkeypatch):
        handshake = json.dumps(
            {"success": True, "data": {"connection_token": "ct-4"}, "error": None}
        )
        ws = _make_mock_ws([handshake])
        _patch_websockets(monkeypatch, ws)
        sso_service._sessions.clear()

        session_uuid, _ = await sso_service.start_sso()
        assert sso_service.cancel_sso(session_uuid) is True
        assert session_uuid not in sso_service._sessions

    def test_cancel_returns_false_for_unknown_uuid(self):
        sso_service._sessions.clear()
        assert sso_service.cancel_sso("missing") is False

    async def test_max_concurrent_sessions_raises(self):
        sso_service._sessions.clear()
        for i in range(sso_service.MAX_CONCURRENT_SESSIONS):
            session = sso_service.SSOSession(uuid=f"injected-{i}")
            session.status = sso_service.SSOStatus.PENDING
            sso_service._sessions[session.uuid] = session

        with pytest.raises(RuntimeError, match="Too many active SSO sessions"):
            await sso_service.start_sso()

        sso_service._sessions.clear()
