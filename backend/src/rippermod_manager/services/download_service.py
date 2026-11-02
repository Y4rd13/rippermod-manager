"""Download orchestration service for Nexus Mods files."""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import httpx
from sqlmodel import Session, col, select

from rippermod_manager.database import engine
from rippermod_manager.models.download import DownloadJob
from rippermod_manager.models.game import Game
from rippermod_manager.nexus.client import (
    NexusClient,
    NexusPremiumRequiredError,
    NexusRateLimitError,
)
from rippermod_manager.services.paths import resolve_mods_dir
from rippermod_manager.services.settings_helpers import get_setting

logger = logging.getLogger(__name__)

# Active cancel events keyed by job_id
_cancel_events: dict[int, asyncio.Event] = {}
# Strong references to background tasks (prevent GC mid-execution)
_background_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]

_PROGRESS_DB_INTERVAL = 5  # seconds between DB progress updates

# Download queue (S6): at most ``download_concurrency`` jobs hold a slot (link
# fetch + transfer); the rest wait as ``queued`` and start oldest id first.
DEFAULT_DOWNLOAD_CONCURRENCY = 3
DOWNLOAD_CONCURRENCY_RANGE = (1, 10)
QUEUED_LINK_EXPIRED = "The Nexus download link expired while queued. Download it again from Nexus."
INTERRUPTED_ERROR = "Interrupted when the app closed"
_IN_FLIGHT_STATUSES = ("queued", "pending", "downloading")


@dataclass
class _QueuedStart:
    """What a queued job needs to start when it gets a slot. Never holds an NXM key."""

    api_key: str
    game_domain: str
    install_path: str
    mods_dir: str | None
    file_name: str
    needs_extension: bool
    # Fetched at request time for NXM (free) requests, while the key is fresh;
    # ``None`` for premium requests, which fetch the link at their slot.
    cdn_url: str | None = None


# Job ids holding a slot, and queued jobs waiting for one, keyed by job id.
_active_job_ids: set[int] = set()
_queued_starts: dict[int, _QueuedStart] = {}


def download_concurrency(session: Session) -> int:
    """The stored ``download_concurrency`` when it is an integer in range, else 3.

    An empty, non-numeric or out-of-range value would mean zero slots (a stuck
    queue) or an unbounded number of transfers, so it falls back to the default.
    """
    raw = (get_setting(session, "download_concurrency") or "").strip()
    if raw.isascii() and raw.isdigit():
        value = int(raw)
        low, high = DOWNLOAD_CONCURRENCY_RANGE
        if low <= value <= high:
            return value
    return DEFAULT_DOWNLOAD_CONCURRENCY


def recover_interrupted_jobs(session: Session) -> int:
    """Mark jobs left in flight by a previous run as failed; return how many.

    The CDN links, NXM keys and transfer tasks lived in memory, so these jobs can
    never finish and would otherwise hold a queue slot forever.
    """
    jobs = session.exec(
        select(DownloadJob).where(
            DownloadJob.status.in_(_IN_FLIGHT_STATUSES)  # type: ignore[union-attr]
        )
    ).all()
    for job in jobs:
        job.status = "failed"
        job.error = INTERRUPTED_ERROR
        session.add(job)
    if jobs:
        session.commit()
    return len(jobs)


def _fail_job(job_id: int, error: str) -> None:
    """Mark a queued job failed; a job cancelled meanwhile stays cancelled."""
    with Session(engine) as s:
        job = s.get(DownloadJob, job_id)
        if job and job.status == "queued":
            job.status = "failed"
            job.error = error[:500]
            s.add(job)
            s.commit()


async def shutdown() -> None:
    """Cancel all active downloads and wait for completion."""
    _queued_starts.clear()
    for event in _cancel_events.values():
        event.set()
    if _background_tasks:
        _, pending = await asyncio.wait(list(_background_tasks), timeout=10.0)
        for task in pending:
            task.cancel()
    _cancel_events.clear()


async def create_and_start_download(
    game: Game,
    nexus_mod_id: int,
    nexus_file_id: int,
    api_key: str,
    session: Session,
    *,
    nxm_key: str | None = None,
    nxm_expires: int | None = None,
) -> DownloadJob:
    """Create a download job and start it, or queue it behind the concurrency cap.

    Returns the job immediately (non-blocking): ``downloading`` when it got a slot,
    ``queued`` when every slot is taken, ``failed`` when no link could be had.
    """
    job = DownloadJob(
        game_id=game.id,  # type: ignore[arg-type]
        nexus_mod_id=nexus_mod_id,
        nexus_file_id=nexus_file_id,
        status="pending",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # Gather data we need before releasing the session
    game_domain = game.domain_name
    install_path = game.install_path
    job_id = job.id
    assert job_id is not None

    async with NexusClient(api_key) as client:
        # Fetch file metadata to get the filename and size
        file_size = 0
        file_name_from_api = False
        try:
            files_resp = await client.get_mod_files(game_domain, nexus_mod_id)
            nexus_files = files_resp.get("files", [])
            target_file = next((f for f in nexus_files if f.get("file_id") == nexus_file_id), None)
            if target_file and target_file.get("file_name"):
                file_name = target_file["file_name"]
                file_name_from_api = True
                file_size = target_file.get("size_in_bytes") or 0
            else:
                file_name = f"mod-{nexus_mod_id}-file-{nexus_file_id}.unknown"
        except httpx.HTTPError:
            logger.warning("Could not fetch file metadata for %d/%d", nexus_mod_id, nexus_file_id)
            file_name = f"mod-{nexus_mod_id}-file-{nexus_file_id}.unknown"

        # Sanitize filename to prevent path traversal
        file_name = Path(file_name).name

        # Cancelled while the metadata was fetched: nothing to start or queue.
        session.refresh(job)
        if job.status == "cancelled":
            return job

        entry = _QueuedStart(
            api_key=api_key,
            game_domain=game_domain,
            install_path=install_path,
            mods_dir=game.mods_dir,
            file_name=file_name,
            needs_extension=not file_name_from_api,
        )
        job.file_name = file_name
        if file_size:
            job.total_bytes = file_size
        # Saved now so a later refresh keeps them. The UPDATE writes only these
        # columns, never over a cancel made in the meantime.
        session.add(job)
        session.commit()

        # No await between the check and the reservation: two requests can never
        # both take the last slot.
        has_slot = len(_active_job_ids) < download_concurrency(session)
        if has_slot:
            _active_job_ids.add(job_id)
        elif nxm_key is None:
            # Premium: the link is fetched when the slot frees (S6).
            return _enqueue(job, entry, session)

        # A slot now, or an NXM request whose key may expire before its slot.
        try:
            links = await client.get_download_links(
                game_domain,
                nexus_mod_id,
                nexus_file_id,
                nxm_key=nxm_key,
                nxm_expires=nxm_expires,
            )
        except NexusPremiumRequiredError:
            return await _fail_at_request(
                job, session, "Premium account required for direct downloads", has_slot
            )
        except NexusRateLimitError:
            return await _fail_at_request(
                job, session, "Nexus rate limit reached, try again later", has_slot
            )
        except httpx.HTTPError as exc:
            return await _fail_at_request(
                job, session, f"Could not get the download link: {exc}", has_slot
            )
        except BaseException:
            if has_slot:
                _active_job_ids.discard(job_id)
            raise

    # Cancelled while the link was fetched: the cancel found no event to set, so
    # writing "downloading" or "queued" now would undo it.
    session.refresh(job)
    if job.status == "cancelled":
        if has_slot:
            _active_job_ids.discard(job_id)
            await _start_next_queued()
        return job

    if not links or not links[0].get("URI"):
        return await _fail_at_request(job, session, "No download links returned", has_slot)

    entry.cdn_url = links[0]["URI"]
    if not has_slot:
        return _enqueue(job, entry, session)

    job.status = "downloading"
    session.add(job)
    session.commit()
    session.refresh(job)
    _launch_transfer(job_id, entry, queued_nxm_url=False)
    return job


def _enqueue(job: DownloadJob, entry: _QueuedStart, session: Session) -> DownloadJob:
    """Park *job* as ``queued`` until a slot frees; start it now if one already did."""
    job_id = job.id
    assert job_id is not None
    session.refresh(job)
    if job.status == "cancelled":
        return job
    job.status = "queued"
    session.add(job)
    session.commit()
    session.refresh(job)
    _queued_starts[job_id] = entry
    # A slot may have freed while this request awaited Nexus.
    _schedule_fill()
    return job


async def _fail_at_request(
    job: DownloadJob, session: Session, error: str, held_slot: bool
) -> DownloadJob:
    """Mark *job* failed unless it was cancelled meanwhile; free its slot either way."""
    session.refresh(job)
    if job.status != "cancelled":
        job.status = "failed"
        job.error = error
        session.add(job)
        session.commit()
        session.refresh(job)
    if held_slot:
        _active_job_ids.discard(job.id)  # type: ignore[arg-type]
        await _start_next_queued()
    return job


def _launch_transfer(job_id: int, entry: _QueuedStart, *, queued_nxm_url: bool) -> None:
    cancel_event = asyncio.Event()
    _cancel_events[job_id] = cancel_event
    task = asyncio.create_task(_transfer(job_id, entry, cancel_event, queued_nxm_url))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _schedule_fill() -> None:
    if not _queued_starts:
        return
    task = asyncio.get_running_loop().create_task(_start_next_queued())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _transfer(
    job_id: int, entry: _QueuedStart, cancel_event: asyncio.Event, queued_nxm_url: bool
) -> None:
    """Run one transfer in its slot, then hand the slot to the next queued job."""
    try:
        assert entry.cdn_url is not None
        await _run_download(
            job_id,
            entry.cdn_url,
            entry.install_path,
            entry.file_name,
            cancel_event,
            needs_extension=entry.needs_extension,
            mods_dir=entry.mods_dir,
            queued_nxm_url=queued_nxm_url,
        )
    finally:
        _active_job_ids.discard(job_id)
        await _start_next_queued()


async def _start_next_queued() -> None:
    """Fill every free slot with the oldest queued jobs (lowest id first).

    The cap is read again each time, so a changed ``download_concurrency``
    applies at the next free slot without touching running transfers.
    """
    while _queued_starts:
        with Session(engine) as s:
            cap = download_concurrency(s)
        if len(_active_job_ids) >= cap:
            return
        job_id = min(_queued_starts)
        entry = _queued_starts.pop(job_id)
        _active_job_ids.add(job_id)
        try:
            started = await _start_queued(job_id, entry)
        except BaseException:
            _active_job_ids.discard(job_id)
            raise
        if not started:
            _active_job_ids.discard(job_id)


async def _start_queued(job_id: int, entry: _QueuedStart) -> bool:
    """Start one queued job in the slot it was given; False when it did not start."""
    with Session(engine) as s:
        job = s.get(DownloadJob, job_id)
        if job is None or job.status != "queued":
            return False
        mod_id, file_id = job.nexus_mod_id, job.nexus_file_id

    queued_nxm_url = entry.cdn_url is not None
    if entry.cdn_url is None:
        try:
            async with NexusClient(entry.api_key) as client:
                links = await client.get_download_links(entry.game_domain, mod_id, file_id)
        except NexusPremiumRequiredError:
            _fail_job(job_id, "Premium account required for direct downloads")
            return False
        except NexusRateLimitError:
            _fail_job(job_id, "Nexus rate limit reached, try again later")
            return False
        except httpx.HTTPError as exc:
            _fail_job(job_id, f"Could not get the download link: {exc}")
            return False
        if not links or not links[0].get("URI"):
            _fail_job(job_id, "No download links returned")
            return False
        entry.cdn_url = links[0]["URI"]

    with Session(engine) as s:
        job = s.get(DownloadJob, job_id)
        # Cancelled while its link was being fetched: give the slot back.
        if job is None or job.status != "queued":
            return False
        job.status = "downloading"
        s.add(job)
        s.commit()
    _launch_transfer(job_id, entry, queued_nxm_url=queued_nxm_url)
    return True


def _parse_content_disposition(header: str) -> str | None:
    """Extract filename from a Content-Disposition header value."""
    if not header:
        return None
    # Try filename*= (RFC 5987: charset'language'value) first
    rfc5987 = re.search(
        r"""filename\*\s*=\s*[Uu][Tt][Ff]-8'[^']*'(.+?)(?:;|$)""",
        header,
    )
    if rfc5987:
        name = Path(unquote(rfc5987.group(1))).name
        if name:
            return name
    # Fall back to plain filename=
    for pattern in (
        r"""filename\s*=\s*"([^"]+)"\s*(?:;|$)""",
        r"""filename\s*=\s*([^\s;]+)""",
    ):
        match = re.search(pattern, header, re.IGNORECASE)
        if match:
            name = Path(match.group(1)).name
            if name:
                return name
    return None


async def _run_download(
    job_id: int,
    cdn_url: str,
    install_path: str,
    file_name: str,
    cancel_event: asyncio.Event,
    *,
    needs_extension: bool = False,
    mods_dir: str | None = None,
    queued_nxm_url: bool = False,
) -> None:
    """Background task that streams the download and updates the DB periodically.

    ``queued_nxm_url``: the CDN URL was fetched with an NXM key when the job was
    queued; an HTTP error at the start of the transfer means it expired meanwhile.
    """
    dest_dir = resolve_mods_dir(install_path, mods_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file_name
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")

    last_db_update = 0.0

    def _progress(downloaded: int, total: int) -> None:
        nonlocal last_db_update
        now = asyncio.get_running_loop().time()
        if now - last_db_update < _PROGRESS_DB_INTERVAL:
            return
        last_db_update = now
        # Update progress in DB from the event loop
        try:
            with Session(engine) as s:
                job = s.get(DownloadJob, job_id)
                if job:
                    job.progress_bytes = downloaded
                    job.total_bytes = total
                    s.add(job)
                    s.commit()
        except Exception:
            logger.debug("Failed to update progress for job %d", job_id)

    try:
        import httpx

        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=300.0) as cdn_client,
            cdn_client.stream("GET", cdn_url) as resp,
        ):
            resp.raise_for_status()

            # Resolve filename from CDN Content-Disposition when API didn't provide one
            if needs_extension:
                cdn_name = _parse_content_disposition(resp.headers.get("Content-Disposition", ""))
                if cdn_name:
                    file_name = cdn_name
                    dest_path = dest_dir / file_name
                    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
                    # Update job with resolved filename
                    try:
                        with Session(engine) as s:
                            job = s.get(DownloadJob, job_id)
                            if job:
                                job.file_name = file_name
                                s.add(job)
                                s.commit()
                    except Exception:
                        logger.debug(
                            "Failed to update resolved filename for job %d",
                            job_id,
                        )

            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(part_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65_536):
                    if cancel_event.is_set():
                        raise asyncio.CancelledError("Download cancelled")
                    f.write(chunk)
                    downloaded += len(chunk)
                    _progress(downloaded, total)

        # Validate: reject 0-byte downloads
        final_size = part_path.stat().st_size
        if final_size == 0:
            part_path.unlink(missing_ok=True)
            raise RuntimeError("CDN returned an empty response (0 bytes downloaded)")

        # Atomic move: only place a complete file in the staging folder
        part_path.replace(dest_path)

        with Session(engine) as s:
            job = s.get(DownloadJob, job_id)
            if job:
                job.status = "completed"
                job.completed_at = datetime.now(UTC)
                job.total_bytes = final_size
                job.progress_bytes = final_size
                s.add(job)
                s.commit()
                from rippermod_manager.services.activity_service import record_activity

                record_activity(
                    s,
                    game_id=job.game_id,
                    action="download",
                    target=job.file_name or f"mod {job.nexus_mod_id}",
                )

    except asyncio.CancelledError:
        part_path.unlink(missing_ok=True)
        dest_path.unlink(missing_ok=True)
        with Session(engine) as s:
            job = s.get(DownloadJob, job_id)
            if job:
                job.status = "cancelled"
                s.add(job)
                s.commit()

    except Exception as e:
        part_path.unlink(missing_ok=True)
        logger.exception("Download failed for job %d", job_id)
        expired = queued_nxm_url and isinstance(e, httpx.HTTPStatusError)
        with Session(engine) as s:
            job = s.get(DownloadJob, job_id)
            if job:
                job.status = "failed"
                job.error = QUEUED_LINK_EXPIRED if expired else str(e)[:500]
                s.add(job)
                s.commit()

    finally:
        _cancel_events.pop(job_id, None)


def get_job(job_id: int, session: Session) -> DownloadJob | None:
    return session.get(DownloadJob, job_id)


def list_jobs(game_id: int, session: Session) -> list[DownloadJob]:
    # Clean up old jobs opportunistically
    cleanup_old_jobs(game_id, session)
    return list(
        session.exec(
            select(DownloadJob)
            .where(DownloadJob.game_id == game_id)
            .order_by(col(DownloadJob.created_at).desc())
        ).all()
    )


def cancel_job(job: DownloadJob, session: Session) -> DownloadJob:
    if job.status in ("pending", "queued", "downloading"):
        _queued_starts.pop(job.id, None)  # type: ignore[arg-type]
        job.status = "cancelled"
        session.add(job)
        session.commit()
        session.refresh(job)
        # Signal the background task to stop
        event = _cancel_events.pop(job.id, None)  # type: ignore[arg-type]
        if event:
            event.set()
    return job


def cleanup_old_jobs(game_id: int, session: Session) -> int:
    cutoff = datetime.now(UTC).timestamp() - 86400  # 24 hours
    old_jobs = session.exec(
        select(DownloadJob).where(
            DownloadJob.game_id == game_id,
            DownloadJob.status.in_(["completed", "failed", "cancelled"]),  # type: ignore[union-attr]
        )
    ).all()
    count = 0
    for job in old_jobs:
        if job.created_at.timestamp() < cutoff:
            session.delete(job)
            count += 1
    if count:
        session.commit()
    return count
