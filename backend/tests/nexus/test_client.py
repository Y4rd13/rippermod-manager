import logging
from importlib.metadata import PackageNotFoundError

import httpx
import pytest
import respx

from rippermod_manager import app_info
from rippermod_manager.app_info import app_version
from rippermod_manager.nexus.client import BASE_URL, NexusClient
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient


class TestNexusClient:
    @respx.mock
    @pytest.mark.asyncio
    async def test_validate_success(self):
        respx.get(f"{BASE_URL}/v1/users/validate.json").mock(
            return_value=httpx.Response(200, json={"name": "testuser", "is_premium": True})
        )
        async with NexusClient("fake-key") as client:
            result = await client.validate_key()
        assert result.valid is True
        assert result.username == "testuser"
        assert result.is_premium is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_validate_401(self):
        respx.get(f"{BASE_URL}/v1/users/validate.json").mock(return_value=httpx.Response(401))
        async with NexusClient("bad-key") as client:
            result = await client.validate_key()
        assert result.valid is False
        assert "401" in result.error

    @respx.mock
    @pytest.mark.asyncio
    async def test_validate_network_error(self):
        respx.get(f"{BASE_URL}/v1/users/validate.json").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        async with NexusClient("key") as client:
            result = await client.validate_key()
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_not_entered_raises(self):
        client = NexusClient("key")
        with pytest.raises(RuntimeError, match="not entered"):
            _ = client.client

    @respx.mock
    @pytest.mark.asyncio
    async def test_apikey_header_present(self):
        route = respx.get(f"{BASE_URL}/v1/users/validate.json").mock(
            return_value=httpx.Response(200, json={"name": "u"})
        )
        async with NexusClient("my-secret-key") as client:
            await client.validate_key()
        assert route.calls[0].request.headers["APIKEY"] == "my-secret-key"

    @respx.mock
    @pytest.mark.asyncio
    async def test_identity_headers_present(self):
        route = respx.get(f"{BASE_URL}/v1/users/validate.json").mock(
            return_value=httpx.Response(200, json={"name": "u"})
        )
        async with NexusClient("key") as client:
            await client.validate_key()
        h = route.calls[0].request.headers
        assert h["Application-Name"] == "RipperMod Manager"
        assert h["Application-Version"] == app_version()
        assert h["User-Agent"] == f"RipperModManager/{app_version()}"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_tracked_mods(self):
        respx.get(f"{BASE_URL}/v1/user/tracked_mods.json").mock(
            return_value=httpx.Response(200, json=[{"mod_id": 1}])
        )
        async with NexusClient("key") as client:
            result = await client.get_tracked_mods()
        assert result == [{"mod_id": 1}]

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_mod_info_url(self):
        route = respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/42.json").mock(
            return_value=httpx.Response(200, json={"name": "Test Mod"})
        )
        async with NexusClient("key") as client:
            result = await client.get_mod_info("cyberpunk2077", 42)
        assert result["name"] == "Test Mod"
        assert route.called


def test_app_version_falls_back_to_dev(monkeypatch):
    def _missing(_name):
        raise PackageNotFoundError

    monkeypatch.setattr(app_info, "version", _missing)
    assert app_info.app_version() == "dev"


def test_app_version_reads_package_metadata(monkeypatch):
    monkeypatch.setattr(app_info, "version", lambda name: f"9.8.7-{name}")
    assert app_info.app_version() == "9.8.7-rippermod-manager"


def test_identity_headers_shape(monkeypatch):
    monkeypatch.setattr(app_info, "version", lambda _name: "1.2.3")
    assert app_info.nexus_identity_headers() == {
        "Application-Name": "RipperMod Manager",
        "Application-Version": "1.2.3",
        "User-Agent": "RipperModManager/1.2.3",
    }


def test_log_identity_once_logs_a_single_time(monkeypatch, caplog):
    monkeypatch.setattr(app_info, "version", lambda _name: "1.2.3")
    monkeypatch.setattr(app_info, "_identity_logged", False)
    with caplog.at_level(logging.INFO, logger=app_info.logger.name):
        app_info.log_identity_once()
        app_info.log_identity_once()
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs == ["Nexus client identifies as RipperMod Manager 1.2.3"]


@pytest.mark.asyncio
async def test_clients_log_identity_once_per_process(monkeypatch, caplog):
    monkeypatch.setattr(app_info, "_identity_logged", False)
    with caplog.at_level(logging.INFO, logger=app_info.logger.name):
        async with NexusClient("k"):
            pass
        async with NexusClient("k"):
            pass
        async with NexusGraphQLClient("k"):
            pass
    msgs = [r.getMessage() for r in caplog.records if "identifies as" in r.getMessage()]
    assert len(msgs) == 1
