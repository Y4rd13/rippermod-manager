import logging
from types import TracebackType
from typing import Any, Self

import httpx

from chat_nexus_mod_manager.schemas.nexus import NexusKeyResult

logger = logging.getLogger(__name__)

BASE_URL = "https://api.nexusmods.com"


class NexusClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"APIKEY": self._api_key, "Accept": "application/json"},
            timeout=30.0,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("NexusClient not entered as context manager")
        return self._client

    async def _get(self, path: str) -> Any:
        resp = await self.client.get(path)
        resp.raise_for_status()
        return resp.json()

    async def validate_key(self) -> NexusKeyResult:
        try:
            data = await self._get("/v1/users/validate.json")
            return NexusKeyResult(
                valid=True,
                username=data.get("name", ""),
                is_premium=data.get("is_premium", False),
            )
        except httpx.HTTPStatusError as e:
            return NexusKeyResult(valid=False, error=f"HTTP {e.response.status_code}")
        except httpx.HTTPError as e:
            return NexusKeyResult(valid=False, error=str(e))

    async def get_tracked_mods(self) -> list[dict[str, Any]]:
        return await self._get("/v1/user/tracked_mods.json")

    async def get_endorsements(self) -> list[dict[str, Any]]:
        return await self._get("/v1/user/endorsements.json")

    async def get_mod_info(self, game_domain: str, mod_id: int) -> dict[str, Any]:
        return await self._get(f"/v1/games/{game_domain}/mods/{mod_id}.json")

    async def get_mod_files(self, game_domain: str, mod_id: int) -> dict[str, Any]:
        return await self._get(f"/v1/games/{game_domain}/mods/{mod_id}/files.json")

    async def get_updated_mods(self, game_domain: str, period: str = "1w") -> list[dict[str, Any]]:
        return await self._get(f"/v1/games/{game_domain}/mods/updated.json?period={period}")

    async def md5_search(self, game_domain: str, md5_hash: str) -> list[dict[str, Any]]:
        return await self._get(f"/v1/games/{game_domain}/mods/md5_search/{md5_hash}.json")
