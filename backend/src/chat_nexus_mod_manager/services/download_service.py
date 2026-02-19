"""Download orchestration service for Nexus Mods files."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, col, select

from chat_nexus_mod_manager.models.download import DownloadJob
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.nexus.client import NexusClient, NexusPremiumRequiredError

logger = logging.getLogger(__name__)


async def start_download(
    game: Game,
    nexus_mod_id: int,
    nexus_file_id: int,
    api_key: str,
    session: Session,
    *,
    nxm_key: str | None = None,
    nxm_expires: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> DownloadJob:
    """Download a file from Nexus to downloaded_mods/.

    progress_callback receives (job_id, downloaded_bytes, total_bytes).
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

    async with NexusClient(api_key) as client:
        # Check premium status when no nxm_key
        if not nxm_key:
            key_result = await client.validate_key()
            if not key_result.is_premium:
                return job

        # Fetch file metadata to get the filename
        try:
            files_resp = await client.get_mod_files(game.domain_name, nexus_mod_id)
            nexus_files = files_resp.get("files", [])
            target_file = None
            for f in nexus_files:
                if f.get("file_id") == nexus_file_id:
                    target_file = f
                    break
            if target_file:
                job.file_name = target_file.get("file_name", f"{nexus_mod_id}-{nexus_file_id}.zip")
            else:
                job.file_name = f"{nexus_mod_id}-{nexus_file_id}.zip"
        except Exception:
            logger.warning("Could not fetch file metadata for %d/%d", nexus_mod_id, nexus_file_id)
            job.file_name = f"{nexus_mod_id}-{nexus_file_id}.zip"

        session.add(job)
        session.commit()

        # Fetch download links
        try:
            links = await client.get_download_links(
                game.domain_name,
                nexus_mod_id,
                nexus_file_id,
                nxm_key=nxm_key,
                nxm_expires=nxm_expires,
            )
        except NexusPremiumRequiredError:
            job.status = "failed"
            job.error = "Premium account required for direct downloads"
            session.add(job)
            session.commit()
            return job

        if not links:
            job.status = "failed"
            job.error = "No download links returned"
            session.add(job)
            session.commit()
            return job

        cdn_url = links[0].get("URI", "")
        if not cdn_url:
            job.status = "failed"
            job.error = "Empty CDN URL in download link"
            session.add(job)
            session.commit()
            return job

        # Prepare destination
        dest_dir = Path(game.install_path) / "downloaded_mods"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / job.file_name

        job.status = "downloading"
        session.add(job)
        session.commit()

        job_id = job.id

        def _progress(downloaded: int, total: int) -> None:
            if progress_callback and job_id is not None:
                progress_callback(job_id, downloaded, total)

        try:
            await client.stream_download(
                cdn_url,
                dest_path,
                progress_callback=_progress,
                cancel_event=cancel_event,
            )
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            # Read final size from disk
            if dest_path.exists():
                job.total_bytes = dest_path.stat().st_size
                job.progress_bytes = job.total_bytes
        except asyncio.CancelledError:
            job.status = "cancelled"
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
        except Exception as e:
            logger.exception("Download failed for job %s", job_id)
            job.status = "failed"
            job.error = str(e)[:500]

    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job(job_id: int, session: Session) -> DownloadJob | None:
    return session.get(DownloadJob, job_id)


def list_jobs(game_id: int, session: Session) -> list[DownloadJob]:
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
