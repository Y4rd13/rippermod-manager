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
            # Create 60 mod IDs to force multiple chunks
            mod_ids = list(range(1, 61))

            phase1_calls = 0

            async def _mock_post(url, json):
                nonlocal phase1_calls
                query = json.get("query", "")
                variables = json.get("variables", {})

                # Phase 1: legacyModsByDomain
                if "legacyModsByDomain" in query:
                    phase1_calls += 1
                    ids_input = variables.get("ids", [])
                    nodes = [{"modId": i["modId"], "name": f"Mod{i['modId']}"} for i in ids_input]
                    resp = MagicMock()
                    resp.status_code = 200
                    resp.json.return_value = {"data": {"legacyModsByDomain": {"nodes": nodes}}}
                    resp.raise_for_status = MagicMock()
                    return resp

                # Phase 2: batch_mods alias queries — return empty data
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = {"data": {}}
                resp.raise_for_status = MagicMock()
                return resp

            with patch.object(gql.client, "post", side_effect=_mock_post):
                result = await gql.batch_mods_by_domain("cyberpunk2077", mod_ids)

        assert phase1_calls == 3  # 60 mods / 25 per chunk = 3 batches
        assert len(result) == 60

    @pytest.mark.asyncio
    async def test_phase2_merges_requirements(self):
        async with NexusGraphQLClient("key") as gql:

            async def _mock_post(url, json):
                query = json.get("query", "")

                if "legacyModsByDomain" in query:
                    resp = MagicMock()
                    resp.status_code = 200
                    resp.json.return_value = {
                        "data": {"legacyModsByDomain": {"nodes": [{"modId": 10, "name": "ModA"}]}}
                    }
                    resp.raise_for_status = MagicMock()
                    return resp

                # Phase 2: alias query returns requirements
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = {
                    "data": {
                        "mod_10": {
                            "modId": 10,
                            "name": "ModA",
                            "modRequirements": {
                                "nexusRequirements": {"nodes": [{"modId": 99, "modName": "Dep"}]},
                            },
                        }
                    }
                }
                resp.raise_for_status = MagicMock()
                return resp

            with patch.object(gql.client, "post", side_effect=_mock_post):
                result = await gql.batch_mods_by_domain("cyberpunk2077", [10])

        assert 10 in result
        reqs = result[10].get("modRequirements", {})
        assert reqs["nexusRequirements"]["nodes"][0]["modName"] == "Dep"

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


class TestGetCollectionRevision:
    """Schema lock for the widened collection-revision query — every field
    Collections install (#222) relies on must be in the query string."""

    REQUIRED_QUERY_FIELDS = (
        # collection-level (preview dialog)
        "name",
        "summary",
        "description",
        "tileImage",
        "user",
        "totalDownloads",
        # revision-level (planning + de-dup)
        "revisionNumber",
        "fileSize",
        "createdAt",
        # per-file (download plan)
        "fileId",
        "version",
        "size",
        "uri",
        "modId",
        "author",
        "pictureUrl",
    )

    @pytest.mark.asyncio
    async def test_query_contains_install_manifest_fields(self):
        """Catch any accidental field removal — install code reads these."""
        captured: dict[str, str] = {}

        async def _capture(_url: str, json: dict) -> MagicMock:
            captured["query"] = json["query"]
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"data": {"collectionRevision": {}}}
            resp.raise_for_status = MagicMock()
            return resp

        async with NexusGraphQLClient("key") as gql:
            with patch.object(gql.client, "post", new=_capture):
                await gql.get_collection_revision("foo", 1, "cyberpunk2077")

        query = captured["query"]
        for field in self.REQUIRED_QUERY_FIELDS:
            assert field in query, f"collection-revision query missing field {field!r}"

    @pytest.mark.asyncio
    async def test_unpacks_revision_payload(self):
        """Realistic Nexus response shape round-trips correctly."""
        payload = {
            "id": "rev_uuid",
            "revisionNumber": 7,
            "revisionStatus": "published",
            "createdAt": "2026-05-01T00:00:00Z",
            "updatedAt": "2026-05-10T00:00:00Z",
            "fileSize": 1024,
            "collection": {
                "id": "coll_uuid",
                "slug": "starter-pack",
                "name": "Starter Pack",
                "summary": "Solid baseline mods",
                "description": "long description",
                "endorsements": 42,
                "totalDownloads": 1000,
                "tileImage": {"url": "https://staticdelivery.nexusmods.com/tile.png"},
                "user": {"name": "author", "memberId": 99},
                "game": {"id": 3333, "domainName": "cyberpunk2077", "name": "Cyberpunk 2077"},
                "category": {"name": "Overhaul"},
            },
            "modFiles": [
                {
                    "optional": False,
                    "file": {
                        "fileId": 12345,
                        "name": "Cool Mod Main.zip",
                        "version": "1.2",
                        "size": 5000,
                        "uri": "Cool_Mod_Main-12345.zip",
                        "mod": {
                            "modId": 100,
                            "name": "Cool Mod",
                            "summary": "Does cool things",
                            "author": "alice",
                            "version": "1.2",
                            "pictureUrl": "https://staticdelivery.nexusmods.com/cool.png",
                        },
                    },
                }
            ],
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"collectionRevision": payload}}
        resp.raise_for_status = MagicMock()

        async with NexusGraphQLClient("key") as gql:
            with patch.object(gql.client, "post", new_callable=AsyncMock, return_value=resp):
                result = await gql.get_collection_revision("starter-pack", 7, "cyberpunk2077")

        assert result["revisionNumber"] == 7
        assert result["collection"]["name"] == "Starter Pack"
        assert result["modFiles"][0]["file"]["fileId"] == 12345
        assert result["modFiles"][0]["file"]["mod"]["modId"] == 100
        assert result["modFiles"][0]["optional"] is False

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_revision_absent(self):
        """``None`` revision (slug/rev mismatch) becomes ``{}`` for callers."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"collectionRevision": None}}
        resp.raise_for_status = MagicMock()

        async with NexusGraphQLClient("key") as gql:
            with patch.object(gql.client, "post", new_callable=AsyncMock, return_value=resp):
                result = await gql.get_collection_revision("missing", 99, "cyberpunk2077")

        assert result == {}
