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
            is_premium=True,
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
            is_premium=True,
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
            is_premium=True,
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
            is_premium=True,
        )
        # Simulate first install finishing so the in-progress guard releases.
        _event_queues.pop(row1.id, None)

        row2 = svc.start_install(
            game=game,
            request=req,
            session=session,
            api_key="key",
            preview=_make_preview(),
            is_premium=True,
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
                is_premium=True,
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
                    is_premium=True,
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
                game_domain=game.domain_name,
                install_path=game.install_path,
                mods_dir=None,
                api_key="key",
                mods=mods,
                is_premium=True,
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


# ---------------------------------------------------------------------------
# NXM signal registry (PR G)
# ---------------------------------------------------------------------------


class TestNxmSignalRegistry:
    """Unit coverage for the free-tier wait registry: registration,
    fulfilment via ``try_route_nxm``, skip via ``request_skip_nxm``,
    and cleanup via ``_unregister_nxm_wait``."""

    @pytest.fixture(autouse=True)
    def _clean_signals(self):
        svc._nxm_signals.clear()
        yield
        svc._nxm_signals.clear()

    @pytest.mark.asyncio
    async def test_register_puts_future_in_signals_dict(self):
        future = svc._register_nxm_wait(100, 1001)
        assert (100, 1001) in svc._nxm_signals
        assert svc._nxm_signals[(100, 1001)] is future
        assert not future.done()

    @pytest.mark.asyncio
    async def test_try_route_nxm_fulfils_future(self):
        future = svc._register_nxm_wait(100, 1001)
        assert svc.try_route_nxm(100, 1001, "key-abc", 1234) is True
        result = await future
        assert result == ("key-abc", 1234)

    @pytest.mark.asyncio
    async def test_try_route_nxm_no_waiter_returns_false(self):
        assert svc.try_route_nxm(404, 999, "key", 1) is False

    @pytest.mark.asyncio
    async def test_try_route_nxm_idempotent_after_done(self):
        svc._register_nxm_wait(100, 1001)
        assert svc.try_route_nxm(100, 1001, "k", 1) is True
        # Second call: the registry entry is still there (cleanup happens
        # in the awaiter's finally), but the future is done, so the second
        # routing call must be a no-op and return False.
        assert svc.try_route_nxm(100, 1001, "k2", 2) is False

    @pytest.mark.asyncio
    async def test_request_skip_nxm_raises_skipped_in_awaiter(self):
        future = svc._register_nxm_wait(100, 1001)
        assert svc.request_skip_nxm(100, 1001) is True
        with pytest.raises(svc.CollectionModSkipped):
            await future

    @pytest.mark.asyncio
    async def test_request_skip_nxm_no_waiter_returns_false(self):
        assert svc.request_skip_nxm(404, 999) is False

    @pytest.mark.asyncio
    async def test_unregister_drops_slot(self):
        svc._register_nxm_wait(100, 1001)
        svc._unregister_nxm_wait(100, 1001)
        assert (100, 1001) not in svc._nxm_signals


# ---------------------------------------------------------------------------
# Free-tier orchestrator branch (PR G)
# ---------------------------------------------------------------------------


class TestFreeTierOrchestratorFlow:
    """``_run_install`` with ``is_premium=False`` emits an ``awaiting_nxm``
    event per mod, blocks until ``try_route_nxm`` (or ``request_skip_nxm``)
    fires, then resumes with the routed (key, expires) pair."""

    @pytest.fixture(autouse=True)
    def _clean_module_state(self):
        svc._nxm_signals.clear()
        svc._event_queues.clear()
        yield
        svc._nxm_signals.clear()
        svc._event_queues.clear()

    def _seed_game(self, client, session):
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        client.post(
            "/api/v1/games/",
            json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
        )
        return session.exec(select(Game)).one()

    def _seed_row(self, session, game_id: int, total: int) -> int:
        from rippermod_manager.models.collection import InstalledCollection

        row = InstalledCollection(
            game_id=game_id,
            slug="starter",
            revision_id="r",
            revision_number=1,
            collection_name="Starter",
            author_name="x",
            summary="",
            tile_image_url="",
            status="pending",
            total_mods=total,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id

    def _entry(self, mid: int, fid: int, name: str) -> CollectionModEntry:
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
    async def test_awaits_then_resumes_with_routed_key(self, client, session):
        """Orchestrator emits awaiting_nxm, blocks, then resumes when
        ``try_route_nxm`` fires -- the resolved key is passed to
        ``create_and_start_download``."""
        import asyncio

        from rippermod_manager.models.collection import InstalledCollection
        from rippermod_manager.models.download import DownloadJob

        game = self._seed_game(client, session)
        collection_id = self._seed_row(session, game.id, 1)
        mods = [self._entry(100, 1001, "ModA")]

        captured: list[dict] = []

        async def _capture(**kw):
            captured.append(kw)
            return DownloadJob(
                id=42,
                game_id=game.id,
                nexus_mod_id=kw["nexus_mod_id"],
                nexus_file_id=kw["nexus_file_id"],
                file_name="modA.zip",
                status="downloading",
            )

        completed_job = DownloadJob(
            id=42,
            game_id=game.id,
            nexus_mod_id=100,
            nexus_file_id=1001,
            file_name="modA.zip",
            status="completed",
        )

        svc._event_queues[collection_id] = asyncio.Queue()

        with (
            patch(
                "rippermod_manager.services.download_service.create_and_start_download",
                new=AsyncMock(side_effect=_capture),
            ),
            patch(
                "rippermod_manager.services.collection_install_service._wait_for_download",
                new=AsyncMock(return_value=completed_job),
            ),
            patch(
                "rippermod_manager.services.install_service.install_mod",
                return_value=None,
            ),
            patch(
                "rippermod_manager.services.vfs.deploy_service.deploy",
                return_value=None,
            ),
        ):
            runner = asyncio.create_task(
                svc._run_install(
                    collection_id=collection_id,
                    game_id=game.id,
                    game_domain=game.domain_name,
                    install_path=game.install_path,
                    mods_dir=None,
                    api_key="key",
                    mods=mods,
                    is_premium=False,
                )
            )
            # Wait for the orchestrator to register its wait slot. Polled
            # rather than slept-fixed so the test still passes on a slow CI.
            for _ in range(100):
                if (100, 1001) in svc._nxm_signals:
                    break
                await asyncio.sleep(0.01)
            assert (100, 1001) in svc._nxm_signals, "orchestrator never registered the NXM wait"

            # Hand the orchestrator the key the user "clicked" on Nexus.
            assert svc.try_route_nxm(100, 1001, "user-key", 99999) is True

            await runner

        assert len(captured) == 1
        assert captured[0]["nxm_key"] == "user-key"
        assert captured[0]["nxm_expires"] == 99999

        session.expire_all()
        final = session.get(InstalledCollection, collection_id)
        assert final.status == "installed"
        assert final.completed_mods == 1

    @pytest.mark.asyncio
    async def test_skip_advances_without_download(self, client, session):
        """``request_skip_nxm`` wakes the orchestrator with CollectionModSkipped;
        the mod is counted as skipped and create_and_start_download is NOT
        called for it."""
        import asyncio

        from rippermod_manager.models.collection import InstalledCollection

        game = self._seed_game(client, session)
        collection_id = self._seed_row(session, game.id, 1)
        mods = [self._entry(100, 1001, "ModA")]

        download_mock = AsyncMock()
        svc._event_queues[collection_id] = asyncio.Queue()

        with (
            patch(
                "rippermod_manager.services.download_service.create_and_start_download",
                new=download_mock,
            ),
            patch(
                "rippermod_manager.services.vfs.deploy_service.deploy",
                return_value=None,
            ),
        ):
            runner = asyncio.create_task(
                svc._run_install(
                    collection_id=collection_id,
                    game_id=game.id,
                    game_domain=game.domain_name,
                    install_path=game.install_path,
                    mods_dir=None,
                    api_key="key",
                    mods=mods,
                    is_premium=False,
                )
            )
            for _ in range(100):
                if (100, 1001) in svc._nxm_signals:
                    break
                await asyncio.sleep(0.01)
            assert svc.request_skip_nxm(100, 1001) is True

            await runner

        download_mock.assert_not_called()
        session.expire_all()
        final = session.get(InstalledCollection, collection_id)
        # All-skipped lands in ``partial`` (no failures, just user-chosen
        # skips), per the updated final-status logic.
        assert final.status == "partial"
        assert final.skipped_mods == 1
        assert final.failed_mods == 0

    @pytest.mark.asyncio
    async def test_timeout_marks_failed(self, client, session, monkeypatch):
        """If no one ever routes the NXM key, the wait times out and the
        mod is marked failed."""
        import asyncio

        from rippermod_manager.models.collection import InstalledCollection

        # Force a tiny timeout so the test doesn't actually wait 10 minutes.
        monkeypatch.setattr(svc, "_NXM_AWAIT_TIMEOUT_S", 0.05)

        game = self._seed_game(client, session)
        collection_id = self._seed_row(session, game.id, 1)
        mods = [self._entry(100, 1001, "ModA")]

        download_mock = AsyncMock()
        svc._event_queues[collection_id] = asyncio.Queue()

        with (
            patch(
                "rippermod_manager.services.download_service.create_and_start_download",
                new=download_mock,
            ),
            patch(
                "rippermod_manager.services.vfs.deploy_service.deploy",
                return_value=None,
            ),
        ):
            await svc._run_install(
                collection_id=collection_id,
                game_id=game.id,
                game_domain=game.domain_name,
                install_path=game.install_path,
                mods_dir=None,
                api_key="key",
                mods=mods,
                is_premium=False,
            )

        download_mock.assert_not_called()
        session.expire_all()
        final = session.get(InstalledCollection, collection_id)
        assert final.status == "failed"
        assert final.failed_mods == 1


# ---------------------------------------------------------------------------
# cancel_install (PR G)
# ---------------------------------------------------------------------------


class TestCancelInstall:
    @pytest.fixture(autouse=True)
    def _clean(self):
        svc._background_tasks.clear()
        yield
        svc._background_tasks.clear()

    def test_no_task_returns_false(self):
        assert svc.cancel_install(99999) is False

    @pytest.mark.asyncio
    async def test_cancels_running_task_by_name(self):
        """``cancel_install`` finds the orchestrator task by its
        ``collection-install-{id}`` name and signals ``cancel()``."""
        import asyncio

        # Spawn a long-running task with the orchestrator-style name.
        task = asyncio.create_task(asyncio.sleep(10), name="collection-install-42")
        svc._background_tasks.add(task)
        try:
            assert svc.cancel_install(42) is True
            # Give the cancel time to propagate.
            with pytest.raises(asyncio.CancelledError):
                await task
            assert task.cancelled()
        finally:
            svc._background_tasks.discard(task)

    @pytest.mark.asyncio
    async def test_already_done_task_returns_false(self):
        """A finished task is not cancelled again (defensive guard)."""
        import asyncio

        async def _noop():
            return None

        done_task = asyncio.create_task(_noop(), name="collection-install-7")
        await done_task
        svc._background_tasks.add(done_task)
        try:
            assert svc.cancel_install(7) is False
        finally:
            svc._background_tasks.discard(done_task)


# ---------------------------------------------------------------------------
# recover_stale_installs (PR G)
# ---------------------------------------------------------------------------


class TestRecoverStaleInstalls:
    """On backend startup, any row left in a non-terminal status is marked
    failed because the in-memory orchestrator state cannot be restored."""

    def _seed_game(self, client, session):
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        client.post(
            "/api/v1/games/",
            json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
        )
        return session.exec(select(Game)).one()

    def _make_row(self, session, game_id: int, slug: str, status: str):
        from rippermod_manager.models.collection import InstalledCollection

        row = InstalledCollection(
            game_id=game_id,
            slug=slug,
            revision_id="r",
            revision_number=1,
            collection_name=slug,
            author_name="x",
            summary="",
            tile_image_url="",
            status=status,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row

    def test_marks_stale_statuses_failed(self, client, session):
        from rippermod_manager.models.collection import InstalledCollection

        game = self._seed_game(client, session)
        ids = {
            status: self._make_row(session, game.id, status, status).id
            for status in (
                "pending",
                "downloading",
                "awaiting_nxm",
                "installing",
            )
        }

        updated = svc.recover_stale_installs(session)
        assert updated == 4

        session.expire_all()
        for status, row_id in ids.items():
            row = session.get(InstalledCollection, row_id)
            assert row.status == "failed", f"row originally {status!r} not updated"
            assert "restarted" in row.error.lower()
            assert row.finished_at is not None

    def test_leaves_terminal_rows_alone(self, client, session):
        from rippermod_manager.models.collection import InstalledCollection

        game = self._seed_game(client, session)
        terminal_ids = {
            status: self._make_row(session, game.id, status, status).id
            for status in ("installed", "partial", "failed", "cancelled")
        }

        updated = svc.recover_stale_installs(session)
        assert updated == 0

        session.expire_all()
        for status, row_id in terminal_ids.items():
            row = session.get(InstalledCollection, row_id)
            assert row.status == status


# ---------------------------------------------------------------------------
# check_updates (PR I)
# ---------------------------------------------------------------------------


def _gql_rev_with_latest(latest_rev: int) -> dict:
    """Trimmed GraphQL revision payload sufficient for check_updates."""
    return {
        "id": "rev_uuid",
        "revisionNumber": 1,
        "collection": {
            "id": "coll_uuid",
            "slug": "x",
            "name": "X",
            "summary": "",
            "description": "",
            "endorsements": 0,
            "totalDownloads": 0,
            "tileImage": {"url": ""},
            "user": {"name": "x", "memberId": 1},
            "game": {"id": 3333, "domainName": "cyberpunk2077", "name": "Cyberpunk 2077"},
            "category": {"name": "x"},
            "latestPublishedRevision": {"revisionNumber": latest_rev},
        },
        "modFiles": [],
    }


class TestCheckUpdates:
    """``check_updates`` fetches the latest revision for every installed
    collection and persists it on the row."""

    def _seed_game(self, client, session):
        from sqlmodel import select

        from rippermod_manager.models.game import Game

        client.post(
            "/api/v1/games/",
            json={"name": "CP", "domain_name": "cyberpunk2077", "install_path": "/cp"},
        )
        return session.exec(select(Game)).one()

    def _seed_row(self, session, game_id: int, slug: str, rev: int):
        from rippermod_manager.models.collection import InstalledCollection

        row = InstalledCollection(
            game_id=game_id,
            slug=slug,
            revision_id="r",
            revision_number=rev,
            collection_name=slug,
            author_name="x",
            summary="",
            tile_image_url="",
            status="installed",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row

    @pytest.mark.asyncio
    async def test_no_installed_collections_returns_empty(self, client, session):
        game = self._seed_game(client, session)
        out = await svc.check_updates(
            session=session, game_id=game.id, game_domain="cyberpunk2077", api_key="k"
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_persists_latest_and_flags_updates(self, client, session):
        from rippermod_manager.models.collection import InstalledCollection

        game = self._seed_game(client, session)
        row1 = self._seed_row(session, game.id, "starter", rev=2)
        row2 = self._seed_row(session, game.id, "expert", rev=5)

        # starter has rev 4 published (newer), expert is up to date at 5.
        async def _fake_get_rev(slug, revision, game_domain):
            return _gql_rev_with_latest(4 if slug == "starter" else 5)

        with patch(
            "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
            new=AsyncMock(side_effect=_fake_get_rev),
        ):
            out = await svc.check_updates(
                session=session,
                game_id=game.id,
                game_domain="cyberpunk2077",
                api_key="k",
            )

        assert len(out) == 2
        by_slug = {r.slug: r for r in out}
        assert by_slug["starter"].latest_revision_number == 4
        assert by_slug["starter"].has_update is True
        assert by_slug["expert"].latest_revision_number == 5
        assert by_slug["expert"].has_update is False

        # Persisted on the rows.
        session.expire_all()
        assert session.get(InstalledCollection, row1.id).latest_known_revision_number == 4
        assert session.get(InstalledCollection, row2.id).latest_known_revision_number == 5

    @pytest.mark.asyncio
    async def test_per_collection_error_does_not_poison_batch(self, client, session):
        from rippermod_manager.nexus.graphql_client import NexusGraphQLError

        game = self._seed_game(client, session)
        self._seed_row(session, game.id, "good", rev=1)
        self._seed_row(session, game.id, "bad", rev=1)

        async def _fake_get_rev(slug, revision, game_domain):
            if slug == "bad":
                raise NexusGraphQLError([{"message": "slug not found"}])
            return _gql_rev_with_latest(2)

        with patch(
            "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
            new=AsyncMock(side_effect=_fake_get_rev),
        ):
            out = await svc.check_updates(
                session=session,
                game_id=game.id,
                game_domain="cyberpunk2077",
                api_key="k",
            )

        by_slug = {r.slug: r for r in out}
        assert by_slug["good"].latest_revision_number == 2
        assert by_slug["good"].error == ""
        assert by_slug["bad"].latest_revision_number is None
        assert by_slug["bad"].error  # truthy
        assert by_slug["bad"].has_update is False

    @pytest.mark.asyncio
    async def test_missing_latest_published_revision_is_error(self, client, session):
        game = self._seed_game(client, session)
        self._seed_row(session, game.id, "x", rev=1)

        # Nexus returned a payload without latestPublishedRevision.
        payload = _gql_rev_with_latest(0)
        del payload["collection"]["latestPublishedRevision"]

        with patch(
            "rippermod_manager.nexus.graphql_client.NexusGraphQLClient.get_collection_revision",
            new=AsyncMock(return_value=payload),
        ):
            out = await svc.check_updates(
                session=session,
                game_id=game.id,
                game_domain="cyberpunk2077",
                api_key="k",
            )

        assert len(out) == 1
        assert out[0].latest_revision_number is None
        assert "latestPublishedRevision" in out[0].error


# ---------------------------------------------------------------------------
# force_reinstall in start_install (PR I)
# ---------------------------------------------------------------------------


class TestForceReinstall:
    """``start_install(force_reinstall=True)`` cascade-uninstalls the
    previous install before kicking off the new one."""

    @pytest.fixture(autouse=True)
    def _no_background(self):
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

    def test_force_reinstall_with_existing_row_cascades(self, client, session):
        """A previous install exists with a child mod -- force_reinstall
        cascades the uninstall (drops the child + the old row) before the
        fresh install row is created."""
        from sqlmodel import select as sql_select

        from rippermod_manager.models.collection import InstalledCollection
        from rippermod_manager.models.install import InstalledMod

        game = self._seed_game(client, session)
        # Seed an existing row + a child mod tagged with it.
        old = InstalledCollection(
            game_id=game.id,
            slug="starter",
            revision_id="old",
            revision_number=1,
            collection_name="Starter",
            author_name="x",
            summary="",
            tile_image_url="",
            status="installed",
        )
        session.add(old)
        session.commit()
        session.refresh(old)
        child = InstalledMod(
            game_id=game.id,
            name="ChildMod",
            source_archive="c.zip",
            installed_collection_id=old.id,
        )
        session.add(child)
        session.commit()

        # Mock uninstall_mod + deploy so the cascade succeeds without touching
        # the real install service.
        with (
            patch(
                "rippermod_manager.services.install_service.uninstall_mod",
                side_effect=lambda mod, _g, s: s.delete(mod) or s.commit(),
            ),
            patch("rippermod_manager.services.vfs.deploy_service.deploy"),
        ):
            req = CollectionInstallRequest(slug="starter", revision=2, force_reinstall=True)
            row = svc.start_install(
                game=game,
                request=req,
                session=session,
                api_key="k",
                preview=_make_preview(),
                is_premium=True,
            )

        # The cascade dropped the old child mod (no leftover rows tied to the
        # old collection's slug). SQLite recycles primary keys after a delete,
        # so we can't compare row.id with old.id directly -- the new row may
        # land on the same numeric id.
        session.expire_all()
        all_rows = session.exec(
            sql_select(InstalledCollection).where(InstalledCollection.slug == "starter")
        ).all()
        assert len(all_rows) == 1, "old + new rows coexisted"
        assert all_rows[0].id == row.id
        assert row.status == "pending"

        # Child mod from the previous install is gone -- proves the cascade ran.
        remaining = session.exec(
            sql_select(InstalledMod).where(InstalledMod.name == "ChildMod")
        ).all()
        assert remaining == []

    def test_force_reinstall_refuses_when_in_progress(self, client, session):
        """Cannot force-reinstall while the install is still running."""
        from rippermod_manager.models.collection import InstalledCollection
        from rippermod_manager.services.collection_install_service import (
            CollectionInstallInProgressError,
            _event_queues,
        )

        game = self._seed_game(client, session)
        existing = InstalledCollection(
            game_id=game.id,
            slug="starter",
            revision_id="r",
            revision_number=1,
            collection_name="Starter",
            author_name="x",
            summary="",
            tile_image_url="",
            status="downloading",
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)

        import asyncio

        _event_queues[existing.id] = asyncio.Queue()
        try:
            req = CollectionInstallRequest(slug="starter", revision=2, force_reinstall=True)
            with pytest.raises(CollectionInstallInProgressError):
                svc.start_install(
                    game=game,
                    request=req,
                    session=session,
                    api_key="k",
                    preview=_make_preview(),
                    is_premium=True,
                )
        finally:
            _event_queues.pop(existing.id, None)

    def test_force_reinstall_with_no_existing_row_is_noop(self, client, session):
        """force_reinstall=True against a fresh game just does a normal install."""
        from sqlmodel import select as sql_select

        from rippermod_manager.models.collection import InstalledCollection

        game = self._seed_game(client, session)
        req = CollectionInstallRequest(slug="starter", revision=1, force_reinstall=True)
        with patch("rippermod_manager.services.vfs.deploy_service.deploy"):
            row = svc.start_install(
                game=game,
                request=req,
                session=session,
                api_key="k",
                preview=_make_preview(),
                is_premium=True,
            )
        assert row.status == "pending"
        # Single row -- no leftover dup from a phantom uninstall.
        rows = session.exec(
            sql_select(InstalledCollection).where(InstalledCollection.slug == "starter")
        ).all()
        assert len(rows) == 1
