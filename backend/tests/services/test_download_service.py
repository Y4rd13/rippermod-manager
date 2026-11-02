import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import select

from rippermod_manager.models.download import DownloadJob
from rippermod_manager.models.settings import AppSetting
from rippermod_manager.services import download_service
from rippermod_manager.services.download_service import (
    INTERRUPTED_ERROR,
    QUEUED_LINK_EXPIRED,
    _parse_content_disposition,
    _run_download,
    cancel_job,
    create_and_start_download,
    download_concurrency,
    recover_interrupted_jobs,
)

CDN_URL = "https://cdn.example.com/test.zip"
ENGINE_ATTR = "rippermod_manager.services.download_service.engine"


class TestParseContentDisposition:
    def test_plain_filename(self):
        header = 'attachment; filename="MyMod-123-1-0.rar"'
        assert _parse_content_disposition(header) == "MyMod-123-1-0.rar"

    def test_unquoted_filename(self):
        header = "attachment; filename=mod.zip"
        assert _parse_content_disposition(header) == "mod.zip"

    def test_utf8_extended_filename_decoded(self):
        header = "attachment; filename*=UTF-8''My%20Mod.7z"
        assert _parse_content_disposition(header) == "My Mod.7z"

    def test_utf8_extended_with_language_tag(self):
        header = "attachment; filename*=UTF-8'en'My%20Mod.7z"
        assert _parse_content_disposition(header) == "My Mod.7z"

    def test_empty_header(self):
        assert _parse_content_disposition("") is None

    def test_no_filename(self):
        assert _parse_content_disposition("attachment") is None

    def test_sanitises_path_traversal(self):
        header = 'attachment; filename="../../etc/passwd"'
        assert _parse_content_disposition(header) == "passwd"

    def test_prefers_extended_over_plain(self):
        header = "attachment; filename*=UTF-8''correct.rar; filename=\"wrong.zip\""
        assert _parse_content_disposition(header) == "correct.rar"


def _make_mock_response(
    chunks: list[bytes],
    headers: dict | None = None,
):
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    resp.headers = headers or {
        "Content-Length": str(sum(len(c) for c in chunks)),
    }

    async def aiter_bytes(chunk_size=65_536):
        for chunk in chunks:
            yield chunk

    resp.aiter_bytes = aiter_bytes
    return resp


def _make_mock_client(resp):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock()

    stream_ctx = AsyncMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=resp)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream.return_value = stream_ctx
    return mock_client


def _run(coro):
    asyncio.run(coro)


class TestRunDownload:
    """Tests for the _run_download background task."""

    @pytest.fixture
    def staging_dir(self, tmp_path):
        d = tmp_path / "game" / "downloaded_mods"
        d.mkdir(parents=True)
        return d

    @pytest.fixture
    def game_dir(self, tmp_path):
        return str(tmp_path / "game")

    @pytest.fixture
    def job_in_db(self, session, make_game):
        game = make_game()
        job = DownloadJob(
            game_id=game.id,
            nexus_mod_id=100,
            nexus_file_id=200,
            file_name="test.zip",
            status="downloading",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    @patch(ENGINE_ATTR)
    def test_successful_download_creates_file(
        self,
        mock_engine,
        session,
        game_dir,
        staging_dir,
        job_in_db,
    ):
        mock_engine.__enter__ = MagicMock(return_value=session)
        resp = _make_mock_response([b"hello ", b"world"])
        client = _make_mock_client(resp)

        with (
            patch("rippermod_manager.services.download_service.Session") as mock_sess,
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_sess.return_value.__enter__ = MagicMock(
                return_value=session,
            )
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            cancel = asyncio.Event()
            _run(
                _run_download(
                    job_in_db.id,
                    CDN_URL,
                    game_dir,
                    "test.zip",
                    cancel,
                )
            )

        dest = staging_dir / "test.zip"
        assert dest.exists()
        assert dest.read_bytes() == b"hello world"
        assert not (staging_dir / "test.zip.part").exists()

    @patch(ENGINE_ATTR)
    def test_failed_download_leaves_no_file(
        self,
        mock_engine,
        session,
        game_dir,
        staging_dir,
        job_in_db,
    ):
        mock_engine.__enter__ = MagicMock(return_value=session)

        async def raise_on_stream(*_a, **_kw):
            raise ConnectionError("CDN connection reset")

        stream_ctx = AsyncMock()
        stream_ctx.__aenter__ = AsyncMock(side_effect=raise_on_stream)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.stream = MagicMock(return_value=stream_ctx)

        with (
            patch("rippermod_manager.services.download_service.Session") as mock_sess,
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_sess.return_value.__enter__ = MagicMock(
                return_value=session,
            )
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            cancel = asyncio.Event()
            _run(
                _run_download(
                    job_in_db.id,
                    CDN_URL,
                    game_dir,
                    "test.zip",
                    cancel,
                )
            )

        assert not (staging_dir / "test.zip").exists()
        assert not (staging_dir / "test.zip.part").exists()

    @patch(ENGINE_ATTR)
    def test_zero_byte_download_marked_as_failed(
        self,
        mock_engine,
        session,
        game_dir,
        staging_dir,
        job_in_db,
    ):
        mock_engine.__enter__ = MagicMock(return_value=session)
        resp = _make_mock_response([], headers={"Content-Length": "0"})
        client = _make_mock_client(resp)

        with (
            patch("rippermod_manager.services.download_service.Session") as mock_sess,
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_sess.return_value.__enter__ = MagicMock(
                return_value=session,
            )
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            cancel = asyncio.Event()
            _run(
                _run_download(
                    job_in_db.id,
                    CDN_URL,
                    game_dir,
                    "test.zip",
                    cancel,
                )
            )

        assert not (staging_dir / "test.zip").exists()
        assert not (staging_dir / "test.zip.part").exists()

    @patch(ENGINE_ATTR)
    def test_cancelled_download_cleans_up(
        self,
        mock_engine,
        session,
        game_dir,
        staging_dir,
        job_in_db,
    ):
        mock_engine.__enter__ = MagicMock(return_value=session)
        cancel = asyncio.Event()

        async def iter_then_cancel(chunk_size=65_536):
            yield b"partial"
            cancel.set()
            yield b"more"

        resp = AsyncMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": "100"}
        resp.aiter_bytes = iter_then_cancel

        client = _make_mock_client(resp)

        with (
            patch("rippermod_manager.services.download_service.Session") as mock_sess,
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_sess.return_value.__enter__ = MagicMock(
                return_value=session,
            )
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            _run(
                _run_download(
                    job_in_db.id,
                    CDN_URL,
                    game_dir,
                    "test.zip",
                    cancel,
                )
            )

        assert not (staging_dir / "test.zip").exists()
        assert not (staging_dir / "test.zip.part").exists()

    @patch(ENGINE_ATTR)
    def test_mid_download_failure_cleans_up_part_file(
        self,
        mock_engine,
        session,
        game_dir,
        staging_dir,
        job_in_db,
    ):
        """Exception during aiter_bytes after partial write cleans .part."""
        mock_engine.__enter__ = MagicMock(return_value=session)

        async def fail_mid_stream(chunk_size=65_536):
            yield b"partial data"
            raise ConnectionError("connection reset mid-stream")

        resp = AsyncMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": "1000"}
        resp.aiter_bytes = fail_mid_stream

        client = _make_mock_client(resp)

        with (
            patch("rippermod_manager.services.download_service.Session") as mock_sess,
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_sess.return_value.__enter__ = MagicMock(
                return_value=session,
            )
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            cancel = asyncio.Event()
            _run(
                _run_download(
                    job_in_db.id,
                    CDN_URL,
                    game_dir,
                    "test.zip",
                    cancel,
                )
            )

        # .part with partial data should have been cleaned up
        assert not (staging_dir / "test.zip.part").exists()
        assert not (staging_dir / "test.zip").exists()

    def test_part_file_not_visible_during_download(self, tmp_path):
        staging = tmp_path / "game" / "downloaded_mods"
        staging.mkdir(parents=True)

        part = staging / "mod.rar.part"
        part.write_bytes(b"partial data")

        assert not (staging / "mod.rar").exists()
        assert part.exists()

        part.rename(staging / "mod.rar")
        assert (staging / "mod.rar").exists()
        assert not part.exists()


class TestStoredNxmUrl:
    @patch(ENGINE_ATTR)
    def test_stored_nxm_url_rejected_at_start_fails_with_the_expiry_text(
        self, mock_engine, session, make_game, tmp_path
    ):
        game = make_game()
        job = DownloadJob(
            game_id=game.id,
            nexus_mod_id=1,
            nexus_file_id=2,
            file_name="q.zip",
            status="downloading",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        resp = _make_mock_response([b"x"])
        request = httpx.Request("GET", CDN_URL)
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "403", request=request, response=httpx.Response(403, request=request)
            )
        )
        client = _make_mock_client(resp)
        with (
            patch("rippermod_manager.services.download_service.Session") as mock_sess,
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_sess.return_value.__enter__ = MagicMock(return_value=session)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            _run(
                _run_download(
                    job.id,
                    CDN_URL,
                    str(tmp_path / "game"),
                    "q.zip",
                    asyncio.Event(),
                    queued_nxm_url=True,
                )
            )
        session.refresh(job)
        assert job.status == "failed" and job.error == QUEUED_LINK_EXPIRED


# ---------------------------------------------------------------------------
# Download queue (S6)
# ---------------------------------------------------------------------------


@pytest.fixture
def queue_env(session, engine, make_game, monkeypatch):
    """A cap of 2, a fake transfer gated per job and a fake Nexus client."""
    monkeypatch.setattr(download_service, "engine", engine)
    monkeypatch.setattr(download_service, "_active_job_ids", set())
    monkeypatch.setattr(download_service, "_queued_starts", {})
    # Tasks left on this test's loop must not reach the app's shutdown in later tests.
    monkeypatch.setattr(download_service, "_background_tasks", set())
    monkeypatch.setattr(download_service, "_cancel_events", {})
    game = make_game()
    started: list[int] = []
    gates: dict[int, asyncio.Event] = {}

    async def fake_run_download(job_id, *_a, **_kw):
        started.append(job_id)
        gate = gates.setdefault(job_id, asyncio.Event())
        await gate.wait()

    monkeypatch.setattr(download_service, "_run_download", fake_run_download)

    nexus = MagicMock()
    nexus.get_mod_files = AsyncMock(
        side_effect=lambda _d, _m: {"files": [{"file_id": 1, "file_name": "f.zip"}]}
    )
    nexus.get_download_links = AsyncMock(return_value=[{"URI": "https://cdn/x"}])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=nexus)
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(download_service, "NexusClient", MagicMock(return_value=ctx))

    session.add(AppSetting(key="download_concurrency", value="2"))
    session.commit()
    return game, started, gates, nexus


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def _request(session, game, n: int, **kw) -> list[DownloadJob]:
    jobs = []
    for i in range(n):
        jobs.append(await create_and_start_download(game, 100 + i, 1, "key", session, **kw))
    await _settle()
    return jobs


def _open_all(gates):
    for gate in gates.values():
        gate.set()


def _status(session, job_id: int) -> str:
    session.expire_all()
    return session.get(DownloadJob, job_id).status


async def test_third_request_is_queued_when_the_cap_is_two(session, queue_env):
    game, started, gates, _nexus = queue_env
    jobs = await _request(session, game, 3)
    ids = [j.id for j in jobs]
    try:
        assert [_status(session, i) for i in ids] == ["downloading", "downloading", "queued"]
        assert started == ids[:2]
    finally:
        _open_all(gates)
        await _settle()


async def test_a_freed_slot_starts_the_oldest_queued(session, queue_env):
    game, started, gates, _nexus = queue_env
    jobs = await _request(session, game, 4)
    ids = [j.id for j in jobs]
    try:
        gates[ids[0]].set()
        await _settle()
        assert started == ids[:3]
        assert _status(session, ids[3]) == "queued"
    finally:
        _open_all(gates)
        await _settle()


async def test_premium_queued_job_asks_for_the_link_at_its_slot(session, queue_env):
    game, _started, gates, nexus = queue_env
    jobs = await _request(session, game, 3)
    try:
        assert nexus.get_download_links.await_count == 2
        gates[jobs[0].id].set()
        await _settle()
        assert nexus.get_download_links.await_count == 3
    finally:
        _open_all(gates)
        await _settle()


async def test_nxm_queued_job_asks_for_the_link_at_request(session, queue_env):
    game, started, gates, nexus = queue_env
    jobs = await _request(session, game, 2)
    third = await create_and_start_download(
        game, 300, 1, "key", session, nxm_key="k", nxm_expires=1
    )
    await _settle()
    try:
        assert _status(session, third.id) == "queued"
        assert nexus.get_download_links.await_count == 3
        assert download_service._queued_starts[third.id].cdn_url == "https://cdn/x"
        gates[jobs[0].id].set()
        await _settle()
        assert started[-1] == third.id
        assert nexus.get_download_links.await_count == 3
    finally:
        _open_all(gates)
        await _settle()


async def test_link_failure_at_the_slot_fails_the_job_and_starts_the_next(session, queue_env):
    from rippermod_manager.nexus.client import NexusPremiumRequiredError

    game, started, gates, nexus = queue_env
    jobs = await _request(session, game, 4)
    ids = [j.id for j in jobs]
    nexus.get_download_links.side_effect = [NexusPremiumRequiredError("x"), [{"URI": "u"}]]
    try:
        gates[ids[0]].set()
        await _settle()
        assert _status(session, ids[2]) == "failed"
        assert started[-1] == ids[3]
    finally:
        _open_all(gates)
        await _settle()


async def test_cancel_works_on_a_queued_job(session, queue_env):
    game, started, gates, _nexus = queue_env
    jobs = await _request(session, game, 3)
    ids = [j.id for j in jobs]
    try:
        job = session.get(DownloadJob, ids[2])
        session.refresh(job)
        assert cancel_job(job, session).status == "cancelled"
        gates[ids[0]].set()
        await _settle()
        assert ids[2] not in started
    finally:
        _open_all(gates)
        await _settle()


async def test_a_lowered_cap_applies_at_the_next_free_slot(session, queue_env):
    game, started, gates, _nexus = queue_env
    jobs = await _request(session, game, 4)
    ids = [j.id for j in jobs]
    setting = session.exec(select(AppSetting).where(AppSetting.key == "download_concurrency")).one()
    setting.value = "1"
    session.add(setting)
    session.commit()
    try:
        gates[ids[0]].set()
        await _settle()
        # One transfer still runs (ids[1]): with a cap of 1 nothing new starts.
        assert started == ids[:2]
        assert _status(session, ids[1]) == "downloading"
    finally:
        _open_all(gates)
        await _settle()


@pytest.mark.parametrize("value", ["", "0", "abc", "11", "-1", "\u00b2"])
def test_concurrency_falls_back_to_default_for_invalid_stored_value(session, value):
    session.add(AppSetting(key="download_concurrency", value=value))
    session.commit()
    assert download_concurrency(session) == 3


@pytest.mark.parametrize("value,expected", [("1", 1), ("10", 10), ("4", 4)])
def test_concurrency_reads_a_valid_stored_value(session, value, expected):
    session.add(AppSetting(key="download_concurrency", value=value))
    session.commit()
    assert download_concurrency(session) == expected


def test_concurrency_defaults_to_three_when_unset(session):
    assert download_concurrency(session) == 3


def test_recover_interrupted_jobs_marks_in_flight_failed(session, make_game):
    game = make_game()
    for status in ("pending", "downloading", "queued", "completed"):
        session.add(DownloadJob(game_id=game.id, nexus_mod_id=1, nexus_file_id=1, status=status))
    session.commit()
    assert recover_interrupted_jobs(session) == 3
    rows = sorted(session.exec(select(DownloadJob)).all(), key=lambda j: j.id)
    assert [j.error for j in rows[:3]] == [INTERRUPTED_ERROR] * 3
    assert [j.status for j in rows] == ["failed", "failed", "failed", "completed"]
