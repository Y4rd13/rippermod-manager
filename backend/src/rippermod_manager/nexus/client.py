import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx

from rippermod_manager.schemas.nexus import NexusKeyResult

logger = logging.getLogger(__name__)

BASE_URL = "https://api.nexusmods.com"

_STREAM_CHUNK_SIZE = 65_536  # 64 KB


class NexusRateLimitError(Exception):
    def __init__(self, hourly_remaining: int, daily_remaining: int, reset: str) -> None:
        self.hourly_remaining = hourly_remaining
        self.daily_remaining = daily_remaining
        self.reset = reset
        super().__init__(f"Rate limited (hourly={hourly_remaining}, daily={daily_remaining})")


class NexusPremiumRequiredError(Exception):
    pass


class NexusClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None
        self.hourly_remaining: int | None = None
        self.daily_remaining: int | None = None

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

    def _read_rate_limit_headers(self, resp: httpx.Response) -> None:
        h_rem = resp.headers.get("X-RL-Hourly-Remaining")
        d_rem = resp.headers.get("X-RL-Daily-Remaining")
        if h_rem is not None:
            self.hourly_remaining = int(h_rem)
        if d_rem is not None:
            self.daily_remaining = int(d_rem)

    async def _get(self, path: str) -> Any:
        resp = await self.client.get(path)
        self._read_rate_limit_headers(resp)
        if resp.status_code == 429:
            raise NexusRateLimitError(
                hourly_remaining=self.hourly_remaining or 0,
                daily_remaining=self.daily_remaining or 0,
                reset=resp.headers.get("X-RL-Hourly-Reset", ""),
            )
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

    async def get_changelogs(self, game_domain: str, mod_id: int) -> dict[str, list[str]]:
        return await self._get(f"/v1/games/{game_domain}/mods/{mod_id}/changelogs.json")

    async def get_mod_files(
        self,
        game_domain: str,
        mod_id: int,
        *,
        category: str | None = None,
    ) -> dict[str, Any]:
        url = f"/v1/games/{game_domain}/mods/{mod_id}/files.json"
        if category:
            url += f"?category={category}"
        return await self._get(url)

    async def get_updated_mods(self, game_domain: str, period: str = "1w") -> list[dict[str, Any]]:
        return await self._get(f"/v1/games/{game_domain}/mods/updated.json?period={period}")

    async def get_latest_updated(self, game_domain: str) -> list[dict[str, Any]]:
        return await self._get(f"/v1/games/{game_domain}/mods/latest_updated.json")

    async def get_trending(self, game_domain: str) -> list[dict[str, Any]]:
        return await self._get(f"/v1/games/{game_domain}/mods/trending.json")

    async def md5_search(self, game_domain: str, md5_hash: str) -> list[dict[str, Any]]:
        return await self._get(f"/v1/games/{game_domain}/mods/md5_search/{md5_hash}.json")

    async def get_download_links(
        self,
        game_domain: str,
        mod_id: int,
        file_id: int,
        *,
        nxm_key: str | None = None,
        nxm_expires: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch CDN download URLs. Premium-only unless nxm_key+nxm_expires provided."""
        path = f"/v1/games/{game_domain}/mods/{mod_id}/files/{file_id}/download_link.json"
        if nxm_key and nxm_expires is not None:
            path += f"?key={nxm_key}&expires={nxm_expires}"
        try:
            return await self._get(path)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise NexusPremiumRequiredError(
                    "Premium account required for direct downloads"
                ) from e
            raise

    async def stream_download(
        self,
        url: str,
        dest: Path,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Stream a file from CDN URL to disk using a separate httpx client."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=300.0) as cdn_client,
            cdn_client.stream("GET", url) as resp,
        ):
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=_STREAM_CHUNK_SIZE):
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("Download cancelled")
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)
