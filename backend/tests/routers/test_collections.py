"""Tests for the Collections HTTP surface (#222 PR C)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

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
    def test_rejects_free_users_with_400(self, client):
        """PR C is premium-only; free users get a 400 pointing at #222."""
        _seed_game(client)
        _set_api_key(client)

        from rippermod_manager.schemas.nexus import NexusKeyResult

        with patch(
            "rippermod_manager.nexus.client.NexusClient.validate_key",
            new=AsyncMock(
                return_value=NexusKeyResult(valid=True, is_premium=False, username="freeuser")
            ),
        ):
            r = client.post(
                "/api/v1/games/CP/collections/install",
                json={"slug": "starter", "revision": 1},
            )
        assert r.status_code == 400
        assert "Premium" in r.json()["detail"]
        assert "#222" in r.json()["detail"]

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
