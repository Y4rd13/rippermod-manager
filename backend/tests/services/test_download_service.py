import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rippermod_manager.models.download import DownloadJob
from rippermod_manager.services.download_service import (
    _parse_content_disposition,
    _run_download,
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
    def job_in_db(self, session):
        job = DownloadJob(
            game_id=1,
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
