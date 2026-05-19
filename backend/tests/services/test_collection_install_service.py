"""Tests for the Collection install orchestrator (#222 PR C)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from rippermod_manager.schemas.collection import (
    CollectionInstallRequest,
    CollectionModEntry,
    CollectionPreviewOut,
)
from rippermod_manager.services import collection_install_service as svc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gql_revision_payload(slug: str = "starter", rev: int = 1) -> dict:
    """Minimal but realistic GraphQL collectionRevision response shape."""
    return {
        "id": "rev_uuid",
        "revisionNumber": rev,
        "revisionStatus": "published",
        "createdAt": "2026-05-01T00:00:00Z",
        "updatedAt": "2026-05-10T00:00:00Z",
        "fileSize": 1024,
        "collection": {
            "id": "coll_uuid",
            "slug": slug,
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
                    "fileId": 1001,
                    "name": "Cool Mod.zip",
                    "version": "1.0",
                    "size": 5000,
                    "uri": "Cool_Mod-1001.zip",
                    "mod": {
                        "modId": 100,
                        "name": "Cool Mod",
                        "summary": "Does cool things",
                        "author": "alice",
                        "version": "1.0",
                        "pictureUrl": "https://staticdelivery.nexusmods.com/100.png",
                    },
                },
            },
            {
                "optional": True,
                "file": {
                    "fileId": 2002,
                    "name": "Optional Mod.zip",
                    "version": "0.5",
                    "size": 1500,
                    "uri": "Optional_Mod-2002.zip",
                    "mod": {
                        "modId": 200,
                        "name": "Optional Mod",
                        "summary": "Nice to have",
                        "author": "bob",
                        "version": "0.5",
                        "pictureUrl": "https://staticdelivery.nexusmods.com/200.png",
                    },
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# _shape_preview
# ---------------------------------------------------------------------------


class TestShapePreview:
    def test_full_payload_unpacks_to_schema(self):
        rev = _gql_revision_payload()
        out = svc._shape_preview("starter", rev)

        assert isinstance(out, CollectionPreviewOut)
        assert out.slug == "starter"
        assert out.revision_id == "rev_uuid"
        assert out.revision_number == 1
        assert out.name == "Starter Pack"
        assert out.author == "author"
        assert out.tile_image_url == "https://staticdelivery.nexusmods.com/tile.png"
        assert out.endorsements == 42
        assert out.total_size_bytes == 5000 + 1500
        assert len(out.mods) == 2
        assert out.mods[0].nexus_mod_id == 100
        assert out.mods[0].nexus_file_id == 1001
        assert out.mods[0].optional is False
        assert out.mods[1].optional is True

    def test_skips_malformed_entries_missing_ids(self):
        rev = _gql_revision_payload()
        rev["modFiles"].append({"optional": False, "file": {}})
        rev["modFiles"].append({"optional": False, "file": {"fileId": 9, "mod": {}}})

        out = svc._shape_preview("starter", rev)
        # The 2 well-formed entries survive, the 2 malformed ones are filtered.
        assert len(out.mods) == 2

    def test_handles_missing_collection_block(self):
        rev = {"revisionNumber": 1, "modFiles": []}
        out = svc._shape_preview("starter", rev)
        assert out.name == ""
        assert out.mods == []


# ---------------------------------------------------------------------------
# fetch_preview
# ---------------------------------------------------------------------------


class TestFetchPreview:
    @pytest.mark.asyncio
    async def test_returns_shaped_preview(self):
        rev = _gql_revision_payload()
        with patch(
            "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
            new=AsyncMock(return_value=rev),
        ):
            out = await svc.fetch_preview("starter", 1, "cyberpunk2077", "fake-key")
        assert out.name == "Starter Pack"
        assert len(out.mods) == 2

    @pytest.mark.asyncio
    async def test_empty_revision_raises_value_error(self):
        """A 404 (no such slug/revision) returns {} from the GraphQL layer."""
        with (
            patch(
                "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
                new=AsyncMock(return_value={}),
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            await svc.fetch_preview("missing", 99, "cyberpunk2077", "fake-key")


# ---------------------------------------------------------------------------
# start_install -- filtering logic
# ---------------------------------------------------------------------------


def _make_preview() -> CollectionPreviewOut:
    return CollectionPreviewOut(
        slug="starter",
        revision_id="rev_uuid",
        revision_number=1,
        name="Starter",
        summary="",
        description="",
        author="author",
        tile_image_url="",
        endorsements=0,
        total_downloads=0,
        total_size_bytes=0,
        mods=[
            CollectionModEntry(
                nexus_mod_id=100,
                nexus_file_id=1001,
                name="Required Mod",
                version="1.0",
                author="alice",
                summary="",
                size_bytes=5000,
                picture_url="",
                optional=False,
            ),
            CollectionModEntry(
                nexus_mod_id=200,
                nexus_file_id=2002,
                name="Optional Mod",
                version="0.5",
                author="bob",
                summary="",
                size_bytes=1500,
                picture_url="",
                optional=True,
            ),
        ],
    )


class TestStartInstallFiltering:
    """start_install applies skip-list + include_optional filters before
    spawning the runner. We patch asyncio.create_task so the background task
    never runs; only the persisted row state matters here.
    """

    @pytest.fixture(autouse=True)
    def _no_background(self):
        with patch(
            "rippermod_manager.services.collection_install_service.asyncio.create_task"
        ) as m:
            m.return_value.add_done_callback = lambda *_: None
            yield

    def _seed_game(self, client, session):
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        client.post(
            "/api/v1/games/",
            json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
        )
        return session.exec(select(Game)).one()

    def test_include_optional_keeps_both(self, client, session):
        game = self._seed_game(client, session)
        req = CollectionInstallRequest(slug="starter", revision=1, include_optional=True)
        row = svc.start_install(
            game=game,
            request=req,
            session=session,
            api_key="key",
            preview=_make_preview(),
        )
        assert row.total_mods == 2

    def test_exclude_optional_drops_optional_mods(self, client, session):
        game = self._seed_game(client, session)
        req = CollectionInstallRequest(slug="starter", revision=1, include_optional=False)
        row = svc.start_install(
            game=game,
            request=req,
            session=session,
            api_key="key",
            preview=_make_preview(),
        )
        assert row.total_mods == 1

    def test_skip_mod_ids_filters_explicitly(self, client, session):
        game = self._seed_game(client, session)
        req = CollectionInstallRequest(
            slug="starter", revision=1, include_optional=True, skip_mod_ids=[100]
        )
        row = svc.start_install(
            game=game,
            request=req,
            session=session,
            api_key="key",
            preview=_make_preview(),
        )
        assert row.total_mods == 1

    def test_reinstall_updates_existing_row(self, client, session):
        """Calling start_install twice for the same (game, slug) updates the
        existing row, never creates a duplicate (per the unique index)."""
        game = self._seed_game(client, session)
        req = CollectionInstallRequest(slug="starter", revision=1)
        row1 = svc.start_install(
            game=game,
            request=req,
            session=session,
            api_key="key",
            preview=_make_preview(),
        )
        row2 = svc.start_install(
            game=game,
            request=req,
            session=session,
            api_key="key",
            preview=_make_preview(),
        )
        assert row1.id == row2.id
        # Status reset on every re-install start.
        assert row2.status == "pending"
        assert row2.completed_mods == 0


# ---------------------------------------------------------------------------
# stream_events -- contract
# ---------------------------------------------------------------------------


class TestStreamEvents:
    @pytest.mark.asyncio
    async def test_no_queue_yields_nothing(self):
        events = [e async for e in svc.stream_events(999_999)]
        assert events == []
