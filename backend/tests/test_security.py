import os
import re
import stat
import sys

import pytest
from fastapi.testclient import TestClient

from rippermod_manager import security
from rippermod_manager.main import app

EVIL = "https://evil.example"


@pytest.fixture
def raw_client(client):
    """Same app and DB as ``client`` but without the token header."""
    with TestClient(app, base_url="http://127.0.0.1:8425", raise_server_exceptions=False) as tc:
        yield tc


def test_api_route_without_token_is_401(raw_client):
    r = raw_client.get("/api/v1/games/")
    assert r.status_code == 401 and r.json() == {"detail": "Unauthorized"}


def test_wrong_token_is_401(raw_client):
    r = raw_client.get("/api/v1/games/", headers={"X-RMM-Token": "0" * 64})
    assert r.status_code == 401 and r.json() == {"detail": "Unauthorized"}


def test_empty_header_is_401(raw_client):
    r = raw_client.get("/api/v1/games/", headers={"X-RMM-Token": ""})
    assert r.status_code == 401


def test_client_with_token_is_200(client):
    assert client.get("/api/v1/games/").status_code == 200


def test_health_is_open(raw_client):
    assert raw_client.get("/health").status_code == 200


def test_deep_health_requires_token(raw_client, client):
    assert raw_client.get("/health/deep").status_code == 401
    assert client.get("/health/deep").status_code in (200, 503)


def test_evil_origin_gets_401_without_cors_header(raw_client):
    r = raw_client.get("/api/v1/games/", headers={"Origin": EVIL})
    assert r.status_code == 401
    assert "access-control-allow-origin" not in r.headers


def test_allowed_origin_gets_cors_header(client):
    r = client.get("/api/v1/games/", headers={"Origin": "http://tauri.localhost"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "access-control-allow-credentials" not in r.headers


def _preflight(c, origin):
    return c.options(
        "/api/v1/games/",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-rmm-token",
        },
    )


def test_preflight_from_tauri_is_200(raw_client):
    r = _preflight(raw_client, "http://tauri.localhost")
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "x-rmm-token" in r.headers["access-control-allow-headers"].lower()


def test_preflight_from_evil_is_400(raw_client):
    assert _preflight(raw_client, EVIL).status_code == 400


def test_evil_host_on_health_is_400(raw_client):
    r = raw_client.get("/health", headers={"Host": "evil.example:8425"})
    assert r.status_code == 400 and r.json() == {"detail": "Invalid host"}


def test_evil_host_with_token_is_400(client):
    assert (
        client.get("/api/v1/games/", headers={"Host": "rebind.evil.example:8425"}).status_code
        == 400
    )


def test_host_check_is_case_insensitive(raw_client):
    assert raw_client.get("/health", headers={"Host": "LocalHost:8425"}).status_code == 200
    assert security.is_allowed_host("LOCALHOST")
    assert security.is_allowed_host("127.0.0.1:8425")


def test_missing_host_is_rejected():
    assert not security.is_allowed_host(None)
    assert not security.is_allowed_host("")


async def _call_without_host(path: str) -> int:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    async def inner(scope, receive, send):
        raise AssertionError("request must not reach the app")

    mw = security.HostAllowlistMiddleware(inner)
    scope = {"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""}
    await mw(scope, receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def test_missing_host_header_is_400():
    import asyncio

    assert asyncio.run(_call_without_host("/health")) == 400


def test_constants_match_spec():
    assert security.TOKEN_HEADER == "X-RMM-Token"
    assert set(security.ALLOWED_ORIGINS) == {
        "tauri://localhost",
        "http://tauri.localhost",
        "http://localhost:1420",
    }
    assert set(security.ALLOWED_HOSTS) == {
        "127.0.0.1:8425",
        "localhost:8425",
        "127.0.0.1",
        "localhost",
    }


def test_env_token_wins_without_file(tmp_path):
    assert security.load_api_token(tmp_path, {"RMM_API_TOKEN": "abc"}) == "abc"
    assert not (tmp_path / "api-token").exists()


def test_empty_env_token_falls_back_to_file(tmp_path):
    token = security.load_api_token(tmp_path, {"RMM_API_TOKEN": ""})
    path = tmp_path / "api-token"
    assert re.fullmatch(r"[0-9a-f]{64}", token)
    assert path.read_text().strip() == token
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # Reused on the next start, so --reload keeps the same token.
    assert security.load_api_token(tmp_path, {"RMM_API_TOKEN": "   "}) == token


def test_garbage_token_file_is_regenerated(tmp_path):
    path = tmp_path / "api-token"
    path.write_text("not-a-token\n")
    token = security.load_api_token(tmp_path, {})
    assert re.fullmatch(r"[0-9a-f]{64}", token)
    assert path.read_text().strip() == token


def test_conftest_token_is_active():
    assert os.environ["RMM_API_TOKEN"]
    assert security.get_api_token() == os.environ["RMM_API_TOKEN"]
