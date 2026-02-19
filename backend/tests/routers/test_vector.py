from unittest.mock import patch


class TestReindex:
    def test_reindex_mock(self, client):
        with patch(
            "chat_nexus_mod_manager.vector.indexer.index_all",
            return_value={"mod_groups": 3, "nexus_mods": 5, "correlations": 2},
        ):
            r = client.post("/api/v1/vector/reindex")
        assert r.status_code == 200
        data = r.json()
        assert data["mod_groups"] == 3
        assert data["nexus_mods"] == 5


class TestSearch:
    def test_requires_q(self, client):
        r = client.get("/api/v1/vector/search")
        assert r.status_code == 422

    def test_returns_results_mock(self, client):
        with patch(
            "chat_nexus_mod_manager.vector.search.semantic_search",
            return_value=[
                {
                    "collection": "mod_groups",
                    "document": "TestMod",
                    "distance": "0.1",
                    "type": "mod_group",
                }
            ],
        ):
            r = client.get("/api/v1/vector/search?q=test")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_n_too_large_422(self, client):
        r = client.get("/api/v1/vector/search?q=test&n=100")
        assert r.status_code == 422


class TestStats:
    def test_returns_3_collections(self, client):
        with patch(
            "chat_nexus_mod_manager.vector.store.get_collection",
        ) as mock_coll:
            mock_coll.return_value.count.return_value = 0
            r = client.get("/api/v1/vector/stats")
        assert r.status_code == 200
        assert len(r.json()) == 3
