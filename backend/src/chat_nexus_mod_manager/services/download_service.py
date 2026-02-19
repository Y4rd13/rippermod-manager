"""Download orchestration service for Nexus Mods files."""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, col, select

from chat_nexus_mod_manager.database import engine
from chat_nexus_mod_manager.models.download import DownloadJob
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.nexus.client import NexusClient, NexusPremiumRequiredError

logger = logging.getLogger(__name__)

# Active cancel events keyed by job_id
_cancel_events: dict[int, asyncio.Event] = {}
# Strong references to background tasks (prevent GC mid-execution)
_background_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]

_PROGRESS_DB_INTERVAL = 5  # seconds between DB progress updates


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
    """Create a download job and kick off the download as a background task.

    Returns the job immediately in "downloading" status (non-blocking).
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
        # Fetch file metadata to get the filename
        try:
            files_resp = await client.get_mod_files(game_domain, nexus_mod_id)
            nexus_files = files_resp.get("files", [])
            target_file = next((f for f in nexus_files if f.get("file_id") == nexus_file_id), None)
            file_name = (
                target_file.get("file_name", f"{nexus_mod_id}-{nexus_file_id}.zip")
                if target_file
                else f"{nexus_mod_id}-{nexus_file_id}.zip"
            )
        except Exception:
            logger.warning("Could not fetch file metadata for %d/%d", nexus_mod_id, nexus_file_id)
            file_name = f"{nexus_mod_id}-{nexus_file_id}.zip"

        # Sanitize filename to prevent path traversal
        file_name = Path(file_name).name

        # Fetch download links (this is fast, do it before backgrounding)
        try:
            links = await client.get_download_links(
                game_domain,
                nexus_mod_id,
                nexus_file_id,
                nxm_key=nxm_key,
                nxm_expires=nxm_expires,
            )
        except NexusPremiumRequiredError:
            job.status = "failed"
            job.error = "Premium account required for direct downloads"
            job.file_name = file_name
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    if not links or not links[0].get("URI"):
        job.status = "failed"
        job.error = "No download links returned"
        job.file_name = file_name
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    cdn_url = links[0]["URI"]

    # Update job with metadata, set to downloading
    job.file_name = file_name
    job.status = "downloading"
    session.add(job)
    session.commit()
    session.refresh(job)

    # Create cancel event and fire background task
    cancel_event = asyncio.Event()
    _cancel_events[job_id] = cancel_event
    task = asyncio.create_task(
        _run_download(job_id, cdn_url, install_path, file_name, cancel_event)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return job


async def _run_download(
    job_id: int,
    cdn_url: str,
    install_path: str,
    file_name: str,
    cancel_event: asyncio.Event,
) -> None:
    """Background task that streams the download and updates the DB periodically."""
    dest_dir = Path(install_path) / "downloaded_mods"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file_name

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
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65_536):
                    if cancel_event.is_set():
                        raise asyncio.CancelledError("Download cancelled")
                    f.write(chunk)
                    downloaded += len(chunk)
                    _progress(downloaded, total)

        # Completed
        with Session(engine) as s:
            job = s.get(DownloadJob, job_id)
            if job:
                job.status = "completed"
                job.completed_at = datetime.now(UTC)
                if dest_path.exists():
                    job.total_bytes = dest_path.stat().st_size
                    job.progress_bytes = job.total_bytes
                s.add(job)
                s.commit()

    except asyncio.CancelledError:
        dest_path.unlink(missing_ok=True)
        with Session(engine) as s:
            job = s.get(DownloadJob, job_id)
            if job:
                job.status = "cancelled"
                s.add(job)
                s.commit()

    except Exception as e:
        logger.exception("Download failed for job %d", job_id)
        with Session(engine) as s:
            job = s.get(DownloadJob, job_id)
            if job:
                job.status = "failed"
                job.error = str(e)[:500]
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
    if job.status in ("pending", "downloading"):
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
