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
        # Mock out the background task spawn and clean leftover queues afterwards
        # so the in-progress guard doesn't false-trip the next test.
        from rippermod_manager.services.collection_install_service import _event_queues

        with patch(
            "rippermod_manager.services.collection_install_service.asyncio.create_task"
        ) as m:
            m.return_value.add_done_callback = lambda *_: None
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
        existing row (after the first install completes), never creates a
        duplicate (per the unique index)."""
        from rippermod_manager.services.collection_install_service import _event_queues

        game = self._seed_game(client, session)
        req = CollectionInstallRequest(slug="starter", revision=1)
        row1 = svc.start_install(
            game=game,
            request=req,
            session=session,
            api_key="key",
            preview=_make_preview(),
        )
        # Simulate first install finishing so the in-progress guard releases.
        _event_queues.pop(row1.id, None)

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


# ---------------------------------------------------------------------------
# In-progress guard (#222 PR C re-review)
# ---------------------------------------------------------------------------


class TestStartInstallGuard:
    """``start_install`` rejects a second concurrent call for the same
    (game, slug) so the in-memory queue does not get clobbered."""

    def _seed_game(self, client, session):
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        client.post(
            "/api/v1/games/",
            json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
        )
        return session.exec(select(Game)).one()

    def test_second_concurrent_install_raises(self, client, session):
        from rippermod_manager.services.collection_install_service import (
            CollectionInstallInProgressError,
            _event_queues,
        )

        game = self._seed_game(client, session)
        req = CollectionInstallRequest(slug="starter", revision=1)
        preview = CollectionPreviewOut(
            slug="starter",
            revision_id="r",
            revision_number=1,
            name="Starter",
            summary="",
            description="",
            author="x",
            tile_image_url="",
            endorsements=0,
            total_downloads=0,
            total_size_bytes=0,
            mods=[],
        )

        with patch(
            "rippermod_manager.services.collection_install_service.asyncio.create_task"
        ) as m:
            m.return_value.add_done_callback = lambda *_: None
            row = svc.start_install(
                game=game,
                request=req,
                session=session,
                api_key="key",
                preview=preview,
            )
        try:
            # While the queue is still registered (simulating an in-flight
            # background task), a second call must refuse.
            assert row.id in _event_queues
            with pytest.raises(CollectionInstallInProgressError) as excinfo:
                svc.start_install(
                    game=game,
                    request=req,
                    session=session,
                    api_key="key",
                    preview=preview,
                )
            assert excinfo.value.collection_id == row.id
        finally:
            _event_queues.pop(row.id, None)


# ---------------------------------------------------------------------------
# _run_install -- happy-path orchestration (#222 PR C re-review feedback)
# ---------------------------------------------------------------------------


class TestRunInstallHappyPath:
    """Integration-ish coverage for the background runner: verifies that
    the download -> install -> deploy sequencing fires in the right order,
    emits the right events, and lands the collection in ``installed``."""

    def _seed_game(self, client, session):
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        client.post(
            "/api/v1/games/",
            json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
        )
        return session.exec(select(Game)).one()

    def _entry(self, *, mid: int, fid: int, name: str) -> CollectionModEntry:
        return CollectionModEntry(
            nexus_mod_id=mid,
            nexus_file_id=fid,
            name=name,
            version="1.0",
            author="alice",
            summary="",
            size_bytes=100,
            picture_url="",
            optional=False,
        )

    @pytest.mark.asyncio
    async def test_happy_path_orchestration(self, client, session):
        """Two mods download + install successfully; deploy runs once at end."""
        from rippermod_manager.models.collection import InstalledCollection
        from rippermod_manager.models.download import DownloadJob

        game = self._seed_game(client, session)

        # Pre-create the InstalledCollection row that _run_install will update.
        row = InstalledCollection(
            game_id=game.id,
            slug="starter",
            revision_id="r",
            revision_number=1,
            collection_name="Starter",
            author_name="x",
            summary="",
            tile_image_url="",
            status="pending",
            total_mods=2,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        collection_id = row.id

        mods = [
            self._entry(mid=100, fid=1001, name="ModA"),
            self._entry(mid=200, fid=2002, name="ModB"),
        ]

        # _wait_for_download polls the DB; simulate completion immediately by
        # returning a fake completed job.
        completed_job = DownloadJob(
            id=999,
            game_id=game.id,
            nexus_mod_id=100,
            nexus_file_id=1001,
            file_name="modA.zip",
            status="completed",
        )

        deploy_called: list[int] = []

        def _fake_deploy(_game, _session):
            deploy_called.append(1)

        # Wire up the queue manually so _emit has a sink, then drain in parallel.
        from rippermod_manager.services.collection_install_service import _event_queues

        _event_queues[collection_id] = __import__("asyncio").Queue()

        async def _drain_events():
            events = []
            async for ev in svc.stream_events(collection_id):
                events.append(ev)
            return events

        # Track install_mod invocations so we can assert the orchestrator
        # routed both mods through the regular (non-FOMOD) install path.
        install_calls: list[str] = []

        def _fake_install_mod(**kw):
            install_calls.append(kw["archive_path"].name)
            # Return a minimal InstalledMod stand-in; the orchestrator does
            # not consume the return value.
            return None

        with (
            patch(
                "rippermod_manager.services.download_service.create_and_start_download",
                new=AsyncMock(
                    side_effect=lambda **kw: DownloadJob(
                        id=kw["nexus_mod_id"],
                        game_id=game.id,
                        nexus_mod_id=kw["nexus_mod_id"],
                        nexus_file_id=kw["nexus_file_id"],
                        file_name=f"mod-{kw['nexus_mod_id']}.zip",
                        status="downloading",
                    )
                ),
            ),
            patch(
                "rippermod_manager.services.collection_install_service._wait_for_download",
                new=AsyncMock(return_value=completed_job),
            ),
            patch(
                "rippermod_manager.services.install_service.install_mod",
                side_effect=_fake_install_mod,
            ),
            patch(
                "rippermod_manager.services.vfs.deploy_service.deploy",
                side_effect=_fake_deploy,
            ),
        ):
            import asyncio

            # Schedule drain first + yield so it blocks on q.get(), THEN run
            # the orchestrator. ``asyncio.Queue.put`` on an unbounded queue
            # is non-blocking, so without this yield the orchestrator races
            # to completion before the drain has a chance to subscribe.
            events_task = asyncio.create_task(_drain_events())
            await asyncio.sleep(0)
            await svc._run_install(
                collection_id=collection_id,
                game_id=game.id,
                install_path=game.install_path,
                mods_dir=None,
                api_key="key",
                mods=mods,
            )
            events = await events_task

        # Sanity: every mod got an install attempt + a deploy at the end.
        assert len(install_calls) == 2
        assert len(deploy_called) == 1

        # Final row state.
        session.expire_all()
        final = session.get(InstalledCollection, collection_id)
        assert final.status == "installed"
        assert final.completed_mods == 2
        assert final.failed_mods == 0
        assert final.skipped_mods == 0
        assert final.finished_at is not None

        # Final SSE event is the ``done`` summary.
        assert events[-1].phase == "done"
        assert events[-1].status == "installed"
        assert events[-1].percent == 100

        # Event sequence includes per-mod download + install phases.
        phases = [e.phase for e in events]
        assert phases.count("download") == 2
        assert phases.count("install") == 2
        assert phases.count("deploy") == 1


# ---------------------------------------------------------------------------
# _install_archive -- FOMOD routing (PR D)
# ---------------------------------------------------------------------------


class TestInstallArchiveRouting:
    """The orchestrator routes between install_mod (regular) and install_fomod
    (when install_mod raises ValueError with "FOMOD" in the message)."""

    def _seed_game(self, client, session):
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        client.post(
            "/api/v1/games/",
            json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
        )
        return session.exec(select(Game)).one()

    def _entry(self, **overrides) -> CollectionModEntry:
        defaults = dict(
            nexus_mod_id=100,
            nexus_file_id=1001,
            name="Mod",
            version="1.0",
            author="alice",
            summary="",
            size_bytes=10,
            picture_url="",
            optional=False,
        )
        defaults.update(overrides)
        return CollectionModEntry(**defaults)

    def test_regular_archive_uses_install_mod_path(self, client, session, tmp_path):
        game = self._seed_game(client, session)
        archive = tmp_path / "regular.zip"
        archive.write_bytes(b"fake zip")

        with (
            patch("rippermod_manager.services.install_service.install_mod") as minstall,
            patch(
                "rippermod_manager.services.collection_install_service._install_fomod_archive"
            ) as mfomod,
            patch("rippermod_manager.services.collection_install_service._tag_installed") as mtag,
        ):
            result = svc._install_archive(
                game=game,
                archive_path=archive,
                entry=self._entry(),
                collection_id=1,
                session=session,
            )

        assert result == "completed"
        minstall.assert_called_once()
        mfomod.assert_not_called()
        mtag.assert_called_once()

    def test_fomod_archive_falls_through_to_fomod_path(self, client, session, tmp_path):
        game = self._seed_game(client, session)
        archive = tmp_path / "fomod.zip"
        archive.write_bytes(b"fake zip")

        with (
            patch(
                "rippermod_manager.services.install_service.install_mod",
                side_effect=ValueError("FOMOD installer detected. ..."),
            ),
            patch(
                "rippermod_manager.services.collection_install_service._install_fomod_archive",
                return_value="completed",
            ) as mfomod,
        ):
            result = svc._install_archive(
                game=game,
                archive_path=archive,
                entry=self._entry(name="MyFomod"),
                collection_id=1,
                session=session,
            )

        assert result == "completed"
        mfomod.assert_called_once()
        kwargs = mfomod.call_args.kwargs
        # mod_name comes from the archive filename (parse_mod_filename), not the
        # entry.name -- mirrors how install_mod identifies installs.
        assert "mod_name" in kwargs

    def test_already_installed_returns_skipped(self, client, session, tmp_path):
        game = self._seed_game(client, session)
        archive = tmp_path / "dup.zip"
        archive.write_bytes(b"x")

        with patch(
            "rippermod_manager.services.install_service.install_mod",
            side_effect=ValueError("Mod 'X' is already installed. Uninstall first..."),
        ):
            result = svc._install_archive(
                game=game,
                archive_path=archive,
                entry=self._entry(),
                collection_id=1,
                session=session,
            )

        assert result == "skipped"

    def test_unexpected_value_error_returns_failed(self, client, session, tmp_path):
        """ValueError that's neither FOMOD nor 'already installed' is a real
        bug -- bubble as 'failed' so the collection counter reflects it."""
        game = self._seed_game(client, session)
        archive = tmp_path / "broken.zip"
        archive.write_bytes(b"x")

        with patch(
            "rippermod_manager.services.install_service.install_mod",
            side_effect=ValueError("Some unrelated validation failure"),
        ):
            result = svc._install_archive(
                game=game,
                archive_path=archive,
                entry=self._entry(),
                collection_id=1,
                session=session,
            )

        assert result == "failed"
