from unittest.mock import AsyncMock

import pytest

from rippermod_manager.services.update_service import _resolve_file_ids


class TestListUpdates:
    def test_game_not_found(self, client):
        r = client.get("/api/v1/games/NoGame/updates/")
        assert r.status_code == 404

    def test_no_correlations_empty(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.get("/api/v1/games/G/updates/")
        assert r.status_code == 200
        data = r.json()
        assert data["total_checked"] == 0
        assert data["updates"] == []

    def test_no_version_diff_empty(self, client, engine):
        from sqlmodel import Session

        from rippermod_manager.models.correlation import ModNexusCorrelation
        from rippermod_manager.models.game import Game, GameModPath
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload, NexusModMeta

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod1")
            s.add(group)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=10, mod_name="Mod1", version="1.0")
            s.add(dl)
            s.flush()
            s.add(
                ModNexusCorrelation(
                    mod_group_id=group.id,
                    nexus_download_id=dl.id,
                    score=1.0,
                    method="exact",
                )
            )
            s.add(NexusModMeta(nexus_mod_id=10, name="Mod1", version="1.0"))
            s.commit()

        r = client.get("/api/v1/games/G/updates/")
        assert r.json()["updates_available"] == 0

    def test_semantic_version_no_false_positive(self, client, engine):
        """'1.0' vs '1.0.0' should NOT be flagged as an update."""
        from sqlmodel import Session

        from rippermod_manager.models.correlation import ModNexusCorrelation
        from rippermod_manager.models.game import Game, GameModPath
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload, NexusModMeta

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod1")
            s.add(group)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=10, mod_name="Mod1", version="1.0")
            s.add(dl)
            s.flush()
            s.add(
                ModNexusCorrelation(
                    mod_group_id=group.id,
                    nexus_download_id=dl.id,
                    score=1.0,
                    method="exact",
                )
            )
            s.add(NexusModMeta(nexus_mod_id=10, name="Mod1", version="1.0.0"))
            s.commit()

        r = client.get("/api/v1/games/G/updates/")
        assert r.json()["updates_available"] == 0

    def test_version_mismatch_returns_update(self, client, engine):
        from sqlmodel import Session

        from rippermod_manager.models.correlation import ModNexusCorrelation
        from rippermod_manager.models.game import Game, GameModPath
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload, NexusModMeta

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod1")
            s.add(group)
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=10,
                mod_name="Mod1",
                version="1.0",
                nexus_url="https://nexus/10",
            )
            s.add(dl)
            s.flush()
            s.add(
                ModNexusCorrelation(
                    mod_group_id=group.id,
                    nexus_download_id=dl.id,
                    score=1.0,
                    method="exact",
                )
            )
            s.add(
                NexusModMeta(
                    nexus_mod_id=10,
                    name="Mod1",
                    version="2.0",
                    author="Auth",
                )
            )
            s.commit()

        r = client.get("/api/v1/games/G/updates/")
        data = r.json()
        assert data["updates_available"] == 1
        assert data["updates"][0]["local_version"] == "1.0"
        assert data["updates"][0]["nexus_version"] == "2.0"

    def test_response_includes_source_field(self, client, engine):
        from sqlmodel import Session

        from rippermod_manager.models.correlation import ModNexusCorrelation
        from rippermod_manager.models.game import Game, GameModPath
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload, NexusModMeta

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod1")
            s.add(group)
            dl = NexusDownload(
                game_id=game.id,
                nexus_mod_id=10,
                mod_name="Mod1",
                version="1.0",
                nexus_url="https://nexus/10",
            )
            s.add(dl)
            s.flush()
            s.add(
                ModNexusCorrelation(
                    mod_group_id=group.id,
                    nexus_download_id=dl.id,
                    score=1.0,
                    method="exact",
                )
            )
            s.add(NexusModMeta(nexus_mod_id=10, name="Mod1", version="3.0", author="A"))
            s.commit()

        r = client.get("/api/v1/games/G/updates/")
        update = r.json()["updates"][0]
        assert update["source"] == "correlation"
        assert update["installed_mod_id"] is None
        assert update["local_timestamp"] is None
        assert update["nexus_timestamp"] is None


class TestCheckUpdates:
    def test_no_key(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.post("/api/v1/games/G/updates/check")
        assert r.status_code == 200
        assert r.json()["total_checked"] == 0

    def test_game_not_found(self, client):
        r = client.post("/api/v1/games/NoGame/updates/check")
        assert r.status_code == 404


class TestResolveFileIds:
    """Tests for the _resolve_file_ids helper."""

    @pytest.mark.anyio
    async def test_picks_most_recent_main_file(self):
        mock_client = AsyncMock()
        mock_client.get_mod_files.return_value = {
            "files": [
                {
                    "file_id": 1,
                    "category_id": 1,
                    "uploaded_timestamp": 1000,
                    "file_name": "old.zip",
                    "version": "1.0",
                },
                {
                    "file_id": 2,
                    "category_id": 1,
                    "uploaded_timestamp": 2000,
                    "file_name": "new.zip",
                    "version": "2.0",
                },
            ]
        }
        updates = [
            {
                "nexus_mod_id": 10,
                "nexus_file_id": None,
                "nexus_version": "2.0",
                "nexus_timestamp": None,
            },
        ]
        await _resolve_file_ids(mock_client, "g", updates)

        assert updates[0]["nexus_file_id"] == 2
        assert updates[0]["nexus_file_name"] == "new.zip"
        assert updates[0]["nexus_version"] == "2.0"
        assert updates[0]["_resolved_file_ts"] == 2000

    @pytest.mark.anyio
    async def test_skips_when_file_id_already_set(self):
        mock_client = AsyncMock()
        updates = [
            {"nexus_mod_id": 10, "nexus_file_id": 99, "nexus_version": "1.0"},
        ]
        await _resolve_file_ids(mock_client, "g", updates)

        mock_client.get_mod_files.assert_not_called()
        assert updates[0]["nexus_file_id"] == 99

    @pytest.mark.anyio
    async def test_falls_back_to_non_archived_file(self):
        """When no MAIN files exist, picks the most recent non-archived file."""
        mock_client = AsyncMock()
        mock_client.get_mod_files.return_value = {
            "files": [
                {
                    "file_id": 5,
                    "category_id": 7,
                    "uploaded_timestamp": 3000,
                    "file_name": "archived.zip",
                    "version": "0.5",
                },
                {
                    "file_id": 6,
                    "category_id": 4,
                    "uploaded_timestamp": 2000,
                    "file_name": "optional.zip",
                    "version": "1.0",
                },
            ]
        }
        updates = [
            {"nexus_mod_id": 10, "nexus_file_id": None, "nexus_version": "1.0"},
        ]
        await _resolve_file_ids(mock_client, "g", updates)

        assert updates[0]["nexus_file_id"] == 6
        assert updates[0]["nexus_file_name"] == "optional.zip"

    @pytest.mark.anyio
    async def test_no_files_leaves_update_unchanged(self):
        mock_client = AsyncMock()
        mock_client.get_mod_files.return_value = {"files": []}
        updates = [
            {"nexus_mod_id": 10, "nexus_file_id": None, "nexus_version": "1.0"},
        ]
        await _resolve_file_ids(mock_client, "g", updates)

        assert updates[0]["nexus_file_id"] is None

    @pytest.mark.anyio
    async def test_api_error_logs_warning_and_continues(self):
        mock_client = AsyncMock()
        mock_client.get_mod_files.side_effect = ValueError("API down")
        updates = [
            {"nexus_mod_id": 10, "nexus_file_id": None, "nexus_version": "1.0"},
        ]
        await _resolve_file_ids(mock_client, "g", updates)

        assert updates[0]["nexus_file_id"] is None
