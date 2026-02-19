import httpx
import pytest
import respx

from chat_nexus_mod_manager.nexus.client import BASE_URL, NexusClient


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
        respx.get(f"{BASE_URL}/v1/users/validate.json").mock(
            return_value=httpx.Response(401)
        )
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
