"""Local API access control: Host allowlist, explicit CORS and a per-launch token.

The backend listens on localhost, which any web page in the user's browser can
reach. Three layers keep the API to the RipperMod window only:

1. ``HostAllowlistMiddleware`` (outermost) answers 400 to any ``Host`` that is
   not a loopback name, which defeats DNS rebinding.
2. ``CORSMiddleware`` only grants the Tauri and Vite dev origins.
3. ``TokenMiddleware`` requires ``X-RMM-Token`` on ``/api/`` and
   ``/health/deep``, compared in constant time with the token of this launch.

All three are pure ASGI so streaming (SSE) responses pass through untouched.
"""

from __future__ import annotations

import functools
import hmac
import json
import logging
import os
import re
import secrets
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

TOKEN_HEADER = "X-RMM-Token"
TOKEN_ENV_VAR = "RMM_API_TOKEN"
TOKEN_FILENAME = "api-token"
ALLOWED_ORIGINS: tuple[str, ...] = (
    "tauri://localhost",
    "http://tauri.localhost",
    "http://localhost:1420",
)
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {"127.0.0.1:8425", "localhost:8425", "127.0.0.1", "localhost"}
)

_TOKEN_RE = re.compile(r"[0-9a-f]{64}")
_TOKEN_HEADER_BYTES = TOKEN_HEADER.lower().encode("latin-1")


def is_allowed_host(host: str | None) -> bool:
    """True when *host* (the ``Host`` header) is a loopback name we serve."""
    if not host:
        return False
    return host.strip().lower() in ALLOWED_HOSTS


def _write_token_file(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 0o600 on POSIX; on Windows the file inherits the per-user ACL of
    # %LOCALAPPDATA%, which already keeps other users out.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(token)
    if sys.platform != "win32":
        os.chmod(path, 0o600)


def load_api_token(data_dir: Path, env: Mapping[str, str]) -> str:
    """Return the token this backend accepts.

    ``RMM_API_TOKEN`` wins when it is set and not blank (Tauri passes it to the
    sidecar). Otherwise, for a backend started by hand in dev, the token lives
    in ``<data_dir>/api-token``: reused when it holds 64 hex characters (so
    ``--reload`` keeps it), regenerated otherwise.
    """
    from_env = env.get(TOKEN_ENV_VAR, "").strip()
    if from_env:
        return from_env
    path = data_dir / TOKEN_FILENAME
    try:
        existing = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        existing = ""
    if _TOKEN_RE.fullmatch(existing):
        return existing
    token = secrets.token_hex(32)
    _write_token_file(path, token)
    logger.info("Wrote a new dev API token to %s", path)
    return token


@functools.cache
def get_api_token() -> str:
    from rippermod_manager.config import settings

    return load_api_token(settings.data_dir, os.environ)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


async def _reject(scope: Scope, send: Send, status: int, detail: str) -> None:
    if scope["type"] == "websocket":
        # Closing before accept makes the server answer the handshake with 403.
        await send({"type": "websocket.close", "code": 1008})
        return
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class HostAllowlistMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and not is_allowed_host(_header(scope, b"host")):
            await _reject(scope, send, 400, "Invalid host")
            return
        await self.app(scope, receive, send)


def _requires_token(path: str) -> bool:
    return path.startswith("/api/") or path == "/health/deep"


class TokenMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and _requires_token(scope.get("path", "")):
            supplied = _header(scope, _TOKEN_HEADER_BYTES) or ""
            expected = get_api_token()
            if not (
                supplied
                and expected
                and hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
            ):
                await _reject(scope, send, 401, "Unauthorized")
                return
        await self.app(scope, receive, send)


def install_security(app: FastAPI) -> None:
    """Register token, CORS and Host middlewares; Host ends up outermost."""
    kwargs: dict[str, Any] = {
        "allow_origins": list(ALLOWED_ORIGINS),
        "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"],
        "allow_headers": ["Content-Type", TOKEN_HEADER],
    }
    app.add_middleware(TokenMiddleware)
    app.add_middleware(CORSMiddleware, **kwargs)
    app.add_middleware(HostAllowlistMiddleware)
