from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rippermod_manager.nexus.graphql_client import NexusGraphQLClient


class TestBatchModsByDomain:
    @pytest.mark.asyncio
    async def test_returns_correct_mapping(self):
        async with NexusGraphQLClient("key") as gql:
            resp_data = {
                "data": {
                    "legacyModsByDomain": {
                        "nodes": [
                            {"modId": 10, "name": "ModA", "uid": "u10"},
                            {"modId": 20, "name": "ModB", "uid": "u20"},
                        ]
                    }
                }
            }
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = resp_data
            mock_resp.raise_for_status = MagicMock()

            with patch.object(gql.client, "post", new_callable=AsyncMock, return_value=mock_resp):
                result = await gql.batch_mods_by_domain("cyberpunk2077", [10, 20])

        assert 10 in result
        assert 20 in result
        assert result[10]["name"] == "ModA"
        assert result[20]["name"] == "ModB"

    @pytest.mark.asyncio
    async def test_chunking_for_large_batches(self):
        async with NexusGraphQLClient("key") as gql:
            # Create 60 mod IDs to force 2 chunks
            mod_ids = list(range(1, 61))

            call_count = 0

            async def _mock_post(url, json):
                nonlocal call_count
                call_count += 1
                ids_input = json.get("variables", {}).get("ids", [])
                nodes = [{"modId": i["modId"], "name": f"Mod{i['modId']}"} for i in ids_input]
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = {"data": {"legacyModsByDomain": {"nodes": nodes}}}
                resp.raise_for_status = MagicMock()
                return resp

            with patch.object(gql.client, "post", side_effect=_mock_post):
                result = await gql.batch_mods_by_domain("cyberpunk2077", mod_ids)

        assert call_count == 3  # 60 mods / 25 per chunk = 3 batches
        assert len(result) == 60

    @pytest.mark.asyncio
    async def test_fallback_on_graphql_error(self):
        async with NexusGraphQLClient("key") as gql:
            # First call fails with GraphQL error
            error_resp = MagicMock()
            error_resp.status_code = 200
            error_resp.json.return_value = {
                "errors": [{"message": "Unknown field legacyModsByDomain"}]
            }
            error_resp.raise_for_status = MagicMock()

            # Fallback batch_mods should be called
            with (
                patch.object(gql.client, "post", new_callable=AsyncMock, return_value=error_resp),
                patch.object(
                    gql,
                    "batch_mods",
                    new_callable=AsyncMock,
                    return_value={10: {"name": "FallbackMod"}},
                ) as mock_fallback,
            ):
                result = await gql.batch_mods_by_domain("cyberpunk2077", [10])

        mock_fallback.assert_called_once_with("cyberpunk2077", [10])
        assert result == {10: {"name": "FallbackMod"}}


class TestSearchMods:
    @pytest.mark.asyncio
    async def test_sort_parameter(self):
        async with NexusGraphQLClient("key") as gql:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"data": {"mods": {"nodes": []}}}
            resp.raise_for_status = MagicMock()

            with patch.object(
                gql.client, "post", new_callable=AsyncMock, return_value=resp
            ) as mock_post:
                await gql.search_mods("cyberpunk2077", "test", sort_by="endorsements")

            call_args = mock_post.call_args
            payload = call_args[1].get("json") or call_args[0][1]
            query = payload["query"]
            variables = payload.get("variables", {})
            assert "$sort" in query
            assert "ModsSort" in query
            sort_var = variables.get("sort", [])
            assert sort_var == [{"field": "endorsements", "direction": "DESC"}]


class TestSearchCollections:
    @pytest.mark.asyncio
    async def test_returns_collection_list(self):
        async with NexusGraphQLClient("key") as gql:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "data": {
                    "collectionsV2": {
                        "nodes": [
                            {"slug": "test-coll", "name": "Test Collection", "endorsements": 100}
                        ]
                    }
                }
            }
            resp.raise_for_status = MagicMock()

            with patch.object(gql.client, "post", new_callable=AsyncMock, return_value=resp):
                result = await gql.search_collections("cyberpunk2077")

        assert len(result) == 1
        assert result[0]["slug"] == "test-coll"
