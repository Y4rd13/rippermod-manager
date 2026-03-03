from types import TracebackType
from typing import Self

from rippermod_manager.nexus.client import NexusClient, NexusRateLimitError
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient, NexusGraphQLError


class NexusAPIClient:
    """Wraps both REST v1 and GraphQL v2 clients."""

    def __init__(self, api_key: str) -> None:
        self.rest = NexusClient(api_key)
        self.gql = NexusGraphQLClient(api_key)

    async def __aenter__(self) -> Self:
        await self.rest.__aenter__()
        try:
            await self.gql.__aenter__()
        except Exception:
            await self.rest.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.gql.__aexit__(exc_type, exc_val, exc_tb)
        await self.rest.__aexit__(exc_type, exc_val, exc_tb)


__all__ = [
    "NexusAPIClient",
    "NexusClient",
    "NexusGraphQLClient",
    "NexusGraphQLError",
    "NexusRateLimitError",
]
