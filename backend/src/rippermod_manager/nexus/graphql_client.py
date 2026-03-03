"""Nexus Mods GraphQL v2 API client.

Provides batch operations (file hashes, mod info), text search,
mod requirements, archive content search, and mutations (endorse/track).
Uses raw httpx POST — no external GraphQL library needed.
"""

import logging
import math
from types import TracebackType
from typing import Any, Self

import httpx

from rippermod_manager.nexus.client import NexusRateLimitError

logger = logging.getLogger(__name__)

GQL_URL = "https://api.nexusmods.com/v2/graphql"

GAME_ID_MAP: dict[str, int] = {
    "cyberpunk2077": 3333,
}

_BATCH_HASH_LIMIT = 500
_BATCH_MOD_ALIAS_LIMIT = 50


class NexusGraphQLError(Exception):
    """Raised when the GraphQL response contains errors."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        msgs = "; ".join(e.get("message", str(e)) for e in errors)
        super().__init__(f"GraphQL errors: {msgs}")


# -- Fragment strings reused across queries ----------------------------------

_MOD_FIELDS = """
    uid
    modId
    name
    summary
    description
    version
    author
    createdAt
    updatedAt
    endorsements
    downloads
    pictureUrl
    category
    modCategory {
        name
    }
    status
"""

_MOD_REQUIREMENT_FIELDS = """
    modRequirements {
        nexusRequirements {
            nodes {
                id
                modId
                modName
                url
                notes
                externalRequirement
                gameId
            }
        }
    }
"""

_MOD_FILE_FIELDS = """
    fileId
    name
    version
    categoryId
    category
    size
    date
    description
"""


class NexusGraphQLClient:
    """Async client for Nexus Mods GraphQL v2 API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            headers={
                "APIKEY": self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=90.0,
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
            raise RuntimeError("NexusGraphQLClient not entered as context manager")
        return self._client

    def _game_id(self, game_domain: str) -> int:
        gid = GAME_ID_MAP.get(game_domain)
        if gid is None:
            raise ValueError(f"Unknown game domain: {game_domain}")
        return gid

    async def _execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        resp = await self.client.post(GQL_URL, json=payload)

        if resp.status_code == 429:
            raise NexusRateLimitError(
                hourly_remaining=0,
                daily_remaining=0,
                reset=resp.headers.get("X-RL-Hourly-Reset", ""),
            )
        resp.raise_for_status()

        data = resp.json()
        if data.get("errors"):
            raise NexusGraphQLError(data["errors"])
        return data.get("data", {})

    # -- Single mod ----------------------------------------------------------

    async def get_mod(self, game_domain: str, mod_id: int) -> dict[str, Any]:
        """Fetch a single mod with requirements."""
        gid = self._game_id(game_domain)
        query = (
            "query GetMod($modId: ID!, $gameId: ID!) {"
            "  mod(modId: $modId, gameId: $gameId) {"
            + _MOD_FIELDS
            + _MOD_REQUIREMENT_FIELDS
            + "  }"
            "}"
        )
        data = await self._execute(query, {"modId": mod_id, "gameId": gid})
        return data.get("mod", {})

    # -- Mod files -----------------------------------------------------------

    async def get_mod_files(self, game_domain: str, mod_id: int) -> list[dict[str, Any]]:
        """Fetch file list for a mod."""
        gid = self._game_id(game_domain)
        query = (
            "query GetModFiles($modId: ID!, $gameId: ID!) {"
            "  modFiles(modId: $modId, gameId: $gameId) {" + _MOD_FILE_FIELDS + "  }"
            "}"
        )
        data = await self._execute(query, {"modId": mod_id, "gameId": gid})
        return data.get("modFiles", [])

    # -- Batch file hashes ---------------------------------------------------

    async def batch_file_hashes(self, md5s: list[str]) -> list[dict[str, Any]]:
        """Batch MD5 lookup (up to 500 per call). Returns flat list of hits."""
        all_hits: list[dict[str, Any]] = []
        chunks = math.ceil(len(md5s) / _BATCH_HASH_LIMIT)
        for i in range(chunks):
            chunk = md5s[i * _BATCH_HASH_LIMIT : (i + 1) * _BATCH_HASH_LIMIT]
            query = """
            query BatchFileHashes($md5s: [String!]!) {
                fileHashes(md5s: $md5s) {
                    md5
                    fileName
                    fileSize
                    gameId
                    modFileId
                    modFile {
                        fileId
                        name
                        version
                        categoryId
                        category
                        size
                        date
                        mod {
                            uid
                            modId
                            name
                            summary
                            version
                            author
                            createdAt
                            updatedAt
                            endorsements
                            downloads
                            pictureUrl
                            category
                            status
                        }
                    }
                }
            }
            """
            data = await self._execute(query, {"md5s": chunk})
            hits = data.get("fileHashes", [])
            if hits:
                all_hits.extend(hits)
        return all_hits

    # -- Batch mods via aliases ----------------------------------------------

    async def batch_mods(self, game_domain: str, mod_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Fetch multiple mods in one query using GraphQL aliases.

        Returns a dict keyed by mod_id.
        """
        gid = self._game_id(game_domain)
        result: dict[int, dict[str, Any]] = {}

        chunks = math.ceil(len(mod_ids) / _BATCH_MOD_ALIAS_LIMIT)
        for i in range(chunks):
            chunk = mod_ids[i * _BATCH_MOD_ALIAS_LIMIT : (i + 1) * _BATCH_MOD_ALIAS_LIMIT]
            aliases = "\n".join(
                f"mod_{mid}: mod(modId: {mid}, gameId: {gid}) {{"
                + _MOD_FIELDS
                + _MOD_REQUIREMENT_FIELDS
                + "}"
                for mid in chunk
            )
            query = f"query BatchMods {{ {aliases} }}"
            data = await self._execute(query)
            for mid in chunk:
                mod_data = data.get(f"mod_{mid}")
                if mod_data:
                    result[mid] = mod_data

        return result

    # -- Text search ---------------------------------------------------------

    async def search_mods(
        self, game_domain: str, name: str, count: int = 20
    ) -> list[dict[str, Any]]:
        """Search mods by name using wildcard filter."""
        gid = self._game_id(game_domain)
        query = (
            "query SearchMods($filter: ModsFilter!, $count: Int!) {"
            "  mods(filter: $filter, count: $count) {"
            "    nodes {" + _MOD_FIELDS + "    }"
            "  }"
            "}"
        )
        variables = {
            "filter": {
                "gameId": [{"value": str(gid), "op": "EQUALS"}],
                "name": [{"value": f"*{name}*", "op": "WILDCARD"}],
            },
            "count": count,
        }
        data = await self._execute(query, variables)
        mods_data = data.get("mods", {})
        return mods_data.get("nodes", [])

    # -- Archive content search ----------------------------------------------

    async def search_file_contents(
        self,
        game_domain: str,
        *,
        file_path_wildcard: str | None = None,
        file_extension: str | None = None,
        count: int = 20,
    ) -> list[dict[str, Any]]:
        """Search inside mod archives by file path or extension."""
        gid = self._game_id(game_domain)
        filter_obj: dict[str, Any] = {"gameId": [{"value": str(gid), "op": "EQUALS"}]}
        if file_path_wildcard:
            filter_obj["filePathWildcard"] = [{"value": file_path_wildcard, "op": "WILDCARD"}]
        if file_extension:
            filter_obj["fileExtensionExact"] = [{"value": file_extension, "op": "EQUALS"}]

        query = """
        query SearchFileContents($filter: ModFileContentSearchFilter!, $count: Int!) {
            modFileContents(filter: $filter, count: $count) {
                nodes {
                    filePath
                    fileSize
                    modFile {
                        fileId
                        name
                        mod {
                            modId
                            name
                        }
                    }
                }
            }
        }
        """
        data = await self._execute(query, {"filter": filter_obj, "count": count})
        contents = data.get("modFileContents", {})
        return contents.get("nodes", [])

    # -- Mutations -----------------------------------------------------------

    async def endorse_mod(self, mod_uid: str) -> dict[str, Any]:
        query = """
        mutation EndorseMod($modUid: String!) {
            createModEndorsement(modUid: $modUid) {
                success
            }
        }
        """
        data = await self._execute(query, {"modUid": mod_uid})
        return data.get("createModEndorsement", {})

    async def abstain_mod(self, mod_uid: str) -> dict[str, Any]:
        query = """
        mutation AbstainMod($modUid: String!) {
            abstainFromModEndorsement(modUid: $modUid) {
                success
            }
        }
        """
        data = await self._execute(query, {"modUid": mod_uid})
        return data.get("abstainFromModEndorsement", {})

    async def track_mod(self, mod_uid: str) -> dict[str, Any]:
        query = """
        mutation TrackMod($modUid: ID!) {
            trackMod(modUid: $modUid) {
                success
            }
        }
        """
        data = await self._execute(query, {"modUid": mod_uid})
        return data.get("trackMod", {})

    async def untrack_mod(self, mod_uid: str) -> dict[str, Any]:
        query = """
        mutation UntrackMod($modUid: ID!) {
            untrackMod(modUid: $modUid) {
                success
            }
        }
        """
        data = await self._execute(query, {"modUid": mod_uid})
        return data.get("untrackMod", {})

    # -- UID helper ----------------------------------------------------------

    async def fetch_mod_uid(self, game_domain: str, mod_id: int) -> str:
        """Fetch the global UID for a mod (needed for mutations)."""
        gid = self._game_id(game_domain)
        query = """
        query GetModUid($modId: ID!, $gameId: ID!) {
            mod(modId: $modId, gameId: $gameId) {
                uid
            }
        }
        """
        data = await self._execute(query, {"modId": mod_id, "gameId": gid})
        mod = data.get("mod", {})
        uid = mod.get("uid", "")
        if not uid:
            raise NexusGraphQLError(
                [{"message": f"No UID returned for mod {mod_id} in {game_domain}"}]
            )
        return uid
