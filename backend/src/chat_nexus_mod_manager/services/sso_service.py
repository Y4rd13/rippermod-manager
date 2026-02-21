"""Nexus Mods SSO service — manages WebSocket-based single sign-on sessions."""

import asyncio
import json
import logging
import time
import uuid as uuid_mod
from dataclasses import dataclass, field
from enum import StrEnum

import websockets

from chat_nexus_mod_manager.schemas.nexus import NexusKeyResult

logger = logging.getLogger(__name__)

SSO_WS_URL = "wss://sso.nexusmods.com"
SSO_AUTHORIZE_URL = "https://www.nexusmods.com/sso"
SSO_TIMEOUT = 300  # 5 minutes
APPLICATION_SLUG = "vortex"  # TODO: replace with registered slug


class SSOStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    EXPIRED = "expired"


@dataclass
class SSOSession:
    uuid: str
    status: SSOStatus = SSOStatus.PENDING
    connection_token: str = ""
    api_key: str = ""
    result: NexusKeyResult | None = None
    error: str = ""
    task: asyncio.Task[None] | None = field(default=None, repr=False)
    created_at: float = field(default_factory=time.monotonic)


_sessions: dict[str, SSOSession] = {}


def _cleanup_expired() -> None:
    """Remove sessions older than SSO_TIMEOUT."""
    now = time.monotonic()
    expired = [k for k, v in _sessions.items() if now - v.created_at > SSO_TIMEOUT]
    for k in expired:
        session = _sessions.pop(k)
        if session.task and not session.task.done():
            session.task.cancel()


async def _sso_listener(session: SSOSession) -> None:
    """Background task: connect to Nexus SSO WebSocket and wait for api_key."""
    try:
        async with websockets.connect(SSO_WS_URL) as ws:
            handshake = json.dumps(
                {
                    "id": session.uuid,
                    "token": None,
                    "protocol": 2,
                }
            )
            await ws.send(handshake)

            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            data = json.loads(raw)
            if not data.get("success"):
                session.status = SSOStatus.ERROR
                session.error = data.get("error", "SSO handshake failed")
                return
            session.connection_token = data["data"]["connection_token"]

            raw = await asyncio.wait_for(ws.recv(), timeout=SSO_TIMEOUT)
            data = json.loads(raw)
            if data.get("success") and data.get("data", {}).get("api_key"):
                session.api_key = data["data"]["api_key"]

                from chat_nexus_mod_manager.nexus.client import NexusClient

                async with NexusClient(session.api_key) as client:
                    result = await client.validate_key()
                session.result = result
                if result.valid:
                    session.status = SSOStatus.SUCCESS
                else:
                    session.status = SSOStatus.ERROR
                    session.error = result.error or "Key validation failed"
            else:
                session.status = SSOStatus.ERROR
                session.error = data.get("error", "Authorization failed")

    except TimeoutError:
        session.status = SSOStatus.EXPIRED
        session.error = "SSO session timed out"
    except websockets.exceptions.ConnectionClosed:
        session.status = SSOStatus.ERROR
        session.error = "WebSocket connection closed unexpectedly"
    except Exception as e:
        logger.exception("SSO listener error")
        session.status = SSOStatus.ERROR
        session.error = str(e)


async def start_sso() -> tuple[str, str]:
    """Start a new SSO session. Returns (uuid, authorize_url)."""
    _cleanup_expired()

    session_uuid = str(uuid_mod.uuid4())
    session = SSOSession(uuid=session_uuid)
    _sessions[session_uuid] = session

    task = asyncio.create_task(_sso_listener(session))
    session.task = task

    # Wait briefly for the connection_token to arrive
    for _ in range(30):
        await asyncio.sleep(0.1)
        if session.connection_token or session.status != SSOStatus.PENDING:
            break

    if session.status == SSOStatus.ERROR:
        error = session.error
        _sessions.pop(session_uuid, None)
        raise RuntimeError(error)

    authorize_url = f"{SSO_AUTHORIZE_URL}?id={session_uuid}&application={APPLICATION_SLUG}"
    return session_uuid, authorize_url


def poll_sso(session_uuid: str) -> SSOSession | None:
    """Check the current status of an SSO session."""
    _cleanup_expired()
    return _sessions.get(session_uuid)


def cancel_sso(session_uuid: str) -> bool:
    """Cancel an active SSO session."""
    session = _sessions.pop(session_uuid, None)
    if session is None:
        return False
    if session.task and not session.task.done():
        session.task.cancel()
    return True
