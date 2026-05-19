"""Tests for the Collections HTTP surface (#222 PR C)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from rippermod_manager.models.collection import InstalledCollection
from rippermod_manager.models.game import Game


def _seed_game(client):
    client.post(
        "/api/v1/games/",
        json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
    )


def _set_api_key(client):
    client.put("/api/v1/settings/", json={"settings": {"nexus_api_key": "valid-key"}})


def _gql_revision_payload(slug: str = "starter") -> dict:
    return {
        "id": "rev_uuid",
        "revisionNumber": 1,
        "revisionStatus": "published",
        "fileSize": 1024,
        "collection": {
            "id": "coll_uuid",
            "slug": slug,
            "name": "Starter Pack",
            "summary": "",
            "description": "",
            "endorsements": 0,
            "totalDownloads": 0,
            "tileImage": {"url": ""},
            "user": {"name": "author", "memberId": 1},
            "game": {"id": 3333, "domainName": "cyberpunk2077", "name": "Cyberpunk 2077"},
        },
        "modFiles": [
            {
                "optional": False,
                "file": {
                    "fileId": 1001,
                    "name": "Cool Mod.zip",
                    "version": "1.0",
                    "size": 5000,
                    "uri": "Cool_Mod-1001.zip",
                    "mod": {
                        "modId": 100,
                        "name": "Cool Mod",
                        "author": "alice",
                        "version": "1.0",
                        "pictureUrl": "",
                    },
                },
            }
        ],
    }


class TestPreview:
    def test_404_when_no_api_key(self, client):
        _seed_game(client)
        r = client.get("/api/v1/games/CP/collections/foo/revision/1/preview")
        assert r.status_code == 400
        assert "API key" in r.json()["detail"]

    def test_404_when_game_missing(self, client):
        _set_api_key(client)
        r = client.get("/api/v1/games/NoGame/collections/foo/revision/1/preview")
        assert r.status_code == 404

    def test_returns_shaped_preview(self, client):
        _seed_game(client)
        _set_api_key(client)
        with patch(
            "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
            new=AsyncMock(return_value=_gql_revision_payload()),
        ):
            r = client.get("/api/v1/games/CP/collections/starter/revision/1/preview")
        assert r.status_code == 200
        body = r.json()
        assert body["slug"] == "starter"
        assert body["name"] == "Starter Pack"
        assert body["author"] == "author"
        assert len(body["mods"]) == 1
        assert body["mods"][0]["nexus_mod_id"] == 100
        assert body["mods"][0]["nexus_file_id"] == 1001

    def test_404_when_revision_missing(self, client):
        _seed_game(client)
        _set_api_key(client)
        with patch(
            "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
            new=AsyncMock(return_value={}),
        ):
            r = client.get("/api/v1/games/CP/collections/missing/revision/99/preview")
        assert r.status_code == 404


class TestInstallKickoff:
    def test_rejects_invalid_api_key_with_401(self, client):
        """``validate_key`` returns ``valid=False`` on a rejected key -- the
        endpoint surfaces that as 401 so the user knows to reconfigure
        Settings rather than seeing a generic 500."""
        _seed_game(client)
        _set_api_key(client)

        from rippermod_manager.schemas.nexus import NexusKeyResult

        with patch(
            "rippermod_manager.nexus.client.NexusClient.validate_key",
            new=AsyncMock(
                return_value=NexusKeyResult(valid=False, is_premium=False, error="HTTP 401")
            ),
        ):
            r = client.post(
                "/api/v1/games/CP/collections/install",
                json={"slug": "starter", "revision": 1},
            )
        assert r.status_code == 401
        assert "reconfigure" in r.json()["detail"].lower()

    def test_free_user_starts_install_with_awaiting_nxm_flow(self, client, session):
        """Free-tier accounts no longer get a 400 -- the orchestrator now
        carries them through the per-file ``awaiting_nxm`` flow (PR G)."""
        _seed_game(client)
        _set_api_key(client)

        from rippermod_manager.schemas.nexus import NexusKeyResult

        with (
            patch(
                "rippermod_manager.nexus.client.NexusClient.validate_key",
                new=AsyncMock(
                    return_value=NexusKeyResult(valid=True, is_premium=False, username="freeuser")
                ),
            ),
            patch(
                "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
                new=AsyncMock(return_value=_gql_revision_payload()),
            ),
            patch(
                "rippermod_manager.services.collection_install_service.asyncio.create_task"
            ) as mtask,
        ):
            mtask.return_value.add_done_callback = lambda *_: None
            r = client.post(
                "/api/v1/games/CP/collections/install",
                json={"slug": "starter", "revision": 1},
            )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["slug"] == "starter"
        assert body["status"] == "pending"
        assert body["total_mods"] == 1

    def test_premium_user_starts_install(self, client, session):
        _seed_game(client)
        _set_api_key(client)

        from rippermod_manager.schemas.nexus import NexusKeyResult

        with (
            patch(
                "rippermod_manager.nexus.client.NexusClient.validate_key",
                new=AsyncMock(
                    return_value=NexusKeyResult(valid=True, is_premium=True, username="premiumuser")
                ),
            ),
            patch(
                "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
                new=AsyncMock(return_value=_gql_revision_payload()),
            ),
            patch(
                "rippermod_manager.services.collection_install_service.asyncio.create_task"
            ) as mtask,
        ):
            mtask.return_value.add_done_callback = lambda *_: None
            r = client.post(
                "/api/v1/games/CP/collections/install",
                json={"slug": "starter", "revision": 1},
            )
        assert r.status_code == 202
        body = r.json()
        assert body["slug"] == "starter"
        assert body["status"] == "pending"
        assert body["total_mods"] == 1

        # Persisted row exists.
        row = session.exec(
            select(InstalledCollection).where(InstalledCollection.slug == "starter")
        ).first()
        assert row is not None
        assert row.collection_name == "Starter Pack"


class TestListAndStatus:
    def test_list_empty(self, client):
        _seed_game(client)
        r = client.get("/api/v1/games/CP/collections")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_returns_seeded_rows(self, client, session):
        _seed_game(client)
        game = session.exec(select(Game)).one()

        session.add(
            InstalledCollection(
                game_id=game.id,
                slug="seeded",
                revision_id="r1",
                revision_number=1,
                collection_name="Seeded",
                author_name="author",
                summary="",
                tile_image_url="",
                status="installed",
                started_at=datetime.now(UTC),
                total_mods=3,
                completed_mods=3,
            )
        )
        session.commit()

        r = client.get("/api/v1/games/CP/collections")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["slug"] == "seeded"
        assert body[0]["status"] == "installed"
        assert body[0]["completed_mods"] == 3

    def test_status_404_when_missing(self, client):
        r = client.get("/api/v1/collections/99999/status")
        assert r.status_code == 404

    def test_status_returns_snapshot(self, client, session):
        _seed_game(client)
        game = session.exec(select(Game)).one()
        row = InstalledCollection(
            game_id=game.id,
            slug="abc",
            revision_id="r",
            revision_number=1,
            collection_name="ABC",
            author_name="x",
            summary="",
            tile_image_url="",
            status="downloading",
            started_at=datetime.now(UTC),
            total_mods=5,
            completed_mods=2,
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        r = client.get(f"/api/v1/collections/{row.id}/status")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "downloading"
        assert body["completed_mods"] == 2


class TestUninstallCollection:
    """``DELETE /api/v1/collections/{id}`` cascades through child mods."""

    @pytest.fixture(autouse=True)
    def _clean_queues(self):
        # The in-memory _event_queues dict is module-level and persists
        # across tests; clear it so leftover queues from earlier install
        # tests do not false-trip the in-progress guard.
        from rippermod_manager.services.collection_install_service import _event_queues

        _event_queues.clear()
        yield
        _event_queues.clear()

    def _seed_game(self, client, session):
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        client.post(
            "/api/v1/games/",
            json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
        )
        return session.exec(select(Game)).one()

    def test_404_when_missing(self, client):
        r = client.delete("/api/v1/collections/99999")
        assert r.status_code == 404

    def test_drops_row_and_returns_counts(self, client, session):
        from rippermod_manager.models.collection import InstalledCollection
        from rippermod_manager.models.install import InstalledMod

        game = self._seed_game(client, session)
        row = InstalledCollection(
            game_id=game.id,
            slug="abc",
            revision_id="r",
            revision_number=1,
            collection_name="ABC",
            author_name="x",
            summary="",
            tile_image_url="",
            status="installed",
            started_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        row_id = row.id

        # No children -- straight delete.
        with patch("rippermod_manager.services.vfs.deploy_service.deploy"):
            r = client.delete(f"/api/v1/collections/{row_id}")
        assert r.status_code == 200
        body = r.json()
        assert body == {"removed_mods": 0, "failed_mods": 0}

        # Endpoint deleted via its own session; expire ours so we see the
        # post-commit DB state. Use the cached id since the row is gone.
        session.expire_all()
        assert session.get(InstalledCollection, row_id) is None
        assert (
            session.exec(
                select(InstalledMod).where(InstalledMod.installed_collection_id == row_id)
            ).first()
            is None
        )

    def test_returns_409_when_install_in_progress(self, client, session):
        """Uninstalling an actively-installing collection must refuse."""
        from rippermod_manager.models.collection import InstalledCollection
        from rippermod_manager.services.collection_install_service import _event_queues

        game = self._seed_game(client, session)
        row = InstalledCollection(
            game_id=game.id,
            slug="busy",
            revision_id="r",
            revision_number=1,
            collection_name="Busy",
            author_name="x",
            summary="",
            tile_image_url="",
            status="downloading",
            started_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        # Mark the install as in-flight by registering a queue.
        import asyncio

        _event_queues[row.id] = asyncio.Queue()
        try:
            r = client.delete(f"/api/v1/collections/{row.id}")
            assert r.status_code == 409
            assert "in progress" in r.json()["detail"]
        finally:
            _event_queues.pop(row.id, None)

    def test_cascade_with_partial_failure(self, client, session):
        """If one child uninstall_mod raises (e.g. file locked by game),
        the surviving child must have its FK nulled so the parent delete
        succeeds. Without that, PRAGMA foreign_keys=ON raises IntegrityError
        on the parent delete and the endpoint 500s."""
        from rippermod_manager.models.collection import InstalledCollection
        from rippermod_manager.models.install import InstalledMod

        game = self._seed_game(client, session)
        row = InstalledCollection(
            game_id=game.id,
            slug="partial",
            revision_id="r",
            revision_number=1,
            collection_name="Partial",
            author_name="x",
            summary="",
            tile_image_url="",
            status="installed",
            started_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        row_id = row.id

        # Seed two child mods linked to the collection.
        child_good = InstalledMod(
            game_id=game.id,
            name="GoodMod",
            source_archive="g.zip",
            installed_collection_id=row_id,
        )
        child_bad = InstalledMod(
            game_id=game.id,
            name="BadMod",
            source_archive="b.zip",
            installed_collection_id=row_id,
        )
        session.add(child_good)
        session.add(child_bad)
        session.commit()
        session.refresh(child_good)
        session.refresh(child_bad)
        bad_id = child_bad.id

        # Patch uninstall_mod so the 2nd call raises (mimics game-running
        # file lock). The 1st call deletes its row as normal.
        call_count = {"n": 0}

        def _fake_uninstall(mod, _game, sess):
            call_count["n"] += 1
            if mod.id == bad_id:
                raise OSError("file locked by game")
            sess.delete(mod)
            sess.commit()
            return None

        with (
            patch(
                "rippermod_manager.services.install_service.uninstall_mod",
                side_effect=_fake_uninstall,
            ),
            patch("rippermod_manager.services.vfs.deploy_service.deploy"),
        ):
            r = client.delete(f"/api/v1/collections/{row_id}")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"removed_mods": 1, "failed_mods": 1}

        # Parent row is gone.
        session.expire_all()
        assert session.get(InstalledCollection, row_id) is None
        # Surviving child still exists but is detached (FK nulled).
        survivor = session.get(InstalledMod, bad_id)
        assert survivor is not None
        assert survivor.installed_collection_id is None


class TestSkipPendingNxm:
    """``POST /collections/{id}/skip-pending-nxm`` wakes a waiting
    orchestrator with a CollectionModSkipped signal."""

    @pytest.fixture(autouse=True)
    def _clean_signals(self):
        from rippermod_manager.services.collection_install_service import _nxm_signals

        _nxm_signals.clear()
        yield
        _nxm_signals.clear()

    def test_404_when_collection_missing(self, client):
        r = client.post(
            "/api/v1/collections/99999/skip-pending-nxm",
            json={"nexus_mod_id": 100, "nexus_file_id": 1001},
        )
        assert r.status_code == 404

    def test_no_waiter_returns_ok_false(self, client, session):
        from rippermod_manager.models.collection import InstalledCollection

        _seed_game(client)
        game = session.exec(select(Game)).one()
        row = InstalledCollection(
            game_id=game.id,
            slug="abc",
            revision_id="r",
            revision_number=1,
            collection_name="ABC",
            author_name="x",
            summary="",
            tile_image_url="",
            status="downloading",
            started_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        r = client.post(
            f"/api/v1/collections/{row.id}/skip-pending-nxm",
            json={"nexus_mod_id": 100, "nexus_file_id": 1001},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_with_active_waiter_returns_ok_true(self, client, session):
        from rippermod_manager.models.collection import InstalledCollection
        from rippermod_manager.services import collection_install_service as svc

        _seed_game(client)
        game = session.exec(select(Game)).one()
        row = InstalledCollection(
            game_id=game.id,
            slug="abc",
            revision_id="r",
            revision_number=1,
            collection_name="ABC",
            author_name="x",
            summary="",
            tile_image_url="",
            status="awaiting_nxm",
            started_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        # Register a wait slot like the orchestrator would.
        future = svc._register_nxm_wait(100, 1001)

        r = client.post(
            f"/api/v1/collections/{row.id}/skip-pending-nxm",
            json={"nexus_mod_id": 100, "nexus_file_id": 1001},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True

        # The future is now done with the skipped exception.
        with pytest.raises(svc.CollectionModSkipped):
            await future


class TestCancelCollectionInstall:
    """``POST /collections/{id}/cancel`` signals the running orchestrator."""

    def test_404_when_collection_missing(self, client):
        r = client.post("/api/v1/collections/99999/cancel")
        assert r.status_code == 404

    def test_no_task_returns_ok_false(self, client, session):
        from rippermod_manager.models.collection import InstalledCollection

        _seed_game(client)
        game = session.exec(select(Game)).one()
        row = InstalledCollection(
            game_id=game.id,
            slug="abc",
            revision_id="r",
            revision_number=1,
            collection_name="ABC",
            author_name="x",
            summary="",
            tile_image_url="",
            status="installed",
            started_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        r = client.post(f"/api/v1/collections/{row.id}/cancel")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False


class TestStartDownloadRoutesToCollection:
    """``POST /games/{name}/downloads/`` intercepts NXM keys that match an
    active Collections orchestrator wait, instead of starting a standalone
    download. Routed responses surface ``routed_to_collection=True``."""

    @pytest.fixture(autouse=True)
    def _clean_signals(self):
        from rippermod_manager.services.collection_install_service import _nxm_signals

        _nxm_signals.clear()
        yield
        _nxm_signals.clear()

    @pytest.mark.asyncio
    async def test_routed_when_waiter_present(self, client, session):
        from rippermod_manager.services import collection_install_service as svc

        _seed_game(client)
        _set_api_key(client)

        # Register a wait slot like the orchestrator would.
        future = svc._register_nxm_wait(100, 1001)

        r = client.post(
            "/api/v1/games/CP/downloads/",
            json={
                "nexus_mod_id": 100,
                "nexus_file_id": 1001,
                "nxm_key": "intercepted",
                "nxm_expires": 7777,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["routed_to_collection"] is True
        assert body["job"] is None

        # The orchestrator's wait sees the routed key.
        result = await future
        assert result == ("intercepted", 7777)

    def test_falls_through_to_standalone_when_no_waiter(self, client, session):
        """No matching orchestrator wait -> the normal download path runs."""
        from rippermod_manager.models.download import DownloadJob

        _seed_game(client)
        _set_api_key(client)

        fake_job = DownloadJob(
            id=1,
            game_id=1,
            nexus_mod_id=500,
            nexus_file_id=5000,
            file_name="standalone.zip",
            status="downloading",
        )

        with patch(
            "rippermod_manager.services.download_service.create_and_start_download",
            new=AsyncMock(return_value=fake_job),
        ):
            r = client.post(
                "/api/v1/games/CP/downloads/",
                json={
                    "nexus_mod_id": 500,
                    "nexus_file_id": 5000,
                    "nxm_key": "irrelevant",
                    "nxm_expires": 1234,
                },
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["routed_to_collection"] is False
        assert body["job"] is not None
        assert body["job"]["file_name"] == "standalone.zip"
