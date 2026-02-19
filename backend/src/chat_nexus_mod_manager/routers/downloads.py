import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import engine, get_session
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.settings import AppSetting
from chat_nexus_mod_manager.routers.deps import get_game_or_404
from chat_nexus_mod_manager.schemas.download import (
    DownloadJobOut,
    DownloadRequest,
    DownloadStartResult,
)
from chat_nexus_mod_manager.services import download_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/downloads", tags=["downloads"])


def _get_api_key(session: Session) -> str:
    setting = session.exec(select(AppSetting).where(AppSetting.key == "nexus_api_key")).first()
    if not setting or not setting.value:
        raise HTTPException(400, "Nexus API key not configured")
    return setting.value


def _job_to_out(job) -> DownloadJobOut:
    return DownloadJobOut(
        id=job.id,
        nexus_mod_id=job.nexus_mod_id,
        nexus_file_id=job.nexus_file_id,
        file_name=job.file_name,
        status=job.status,
        progress_bytes=job.progress_bytes,
        total_bytes=job.total_bytes,
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.post("/", response_model=DownloadStartResult)
async def start_download(
    game_name: str,
    body: DownloadRequest,
    session: Session = Depends(get_session),
) -> DownloadStartResult:
    game = get_game_or_404(game_name, session)
    api_key = _get_api_key(session)

    # Check premium status to decide if we can start
    if not body.nxm_key:
        from chat_nexus_mod_manager.nexus.client import NexusClient

        async with NexusClient(api_key) as client:
            key_result = await client.validate_key()

        if not key_result.is_premium:
            # Create a pending job but don't start download
            from chat_nexus_mod_manager.models.download import DownloadJob

            job = DownloadJob(
                game_id=game.id,  # type: ignore[arg-type]
                nexus_mod_id=body.nexus_mod_id,
                nexus_file_id=body.nexus_file_id,
                status="pending",
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return DownloadStartResult(job=_job_to_out(job), requires_nxm=True)

    job = await download_service.start_download(
        game=game,
        nexus_mod_id=body.nexus_mod_id,
        nexus_file_id=body.nexus_file_id,
        api_key=api_key,
        session=session,
        nxm_key=body.nxm_key,
        nxm_expires=body.nxm_expires,
    )

    return DownloadStartResult(job=_job_to_out(job), requires_nxm=False)


@router.get("/", response_model=list[DownloadJobOut])
def list_downloads(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[DownloadJobOut]:
    game = get_game_or_404(game_name, session)
    jobs = download_service.list_jobs(game.id, session)  # type: ignore[arg-type]
    return [_job_to_out(j) for j in jobs]


@router.get("/{job_id}", response_model=DownloadJobOut)
def get_download(
    game_name: str,
    job_id: int,
    session: Session = Depends(get_session),
) -> DownloadJobOut:
    get_game_or_404(game_name, session)
    job = download_service.get_job(job_id, session)
    if not job:
        raise HTTPException(404, "Download job not found")
    return _job_to_out(job)


@router.post("/{job_id}/cancel", response_model=DownloadJobOut)
def cancel_download(
    game_name: str,
    job_id: int,
    session: Session = Depends(get_session),
) -> DownloadJobOut:
    get_game_or_404(game_name, session)
    job = download_service.get_job(job_id, session)
    if not job:
        raise HTTPException(404, "Download job not found")
    job = download_service.cancel_job(job, session)
    return _job_to_out(job)


@router.post("/stream")
async def download_stream(
    game_name: str,
    body: DownloadRequest,
) -> StreamingResponse:
    """Start a download and stream progress as SSE events."""
    progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def run_download() -> None:
        try:
            with Session(engine) as session:
                game = session.exec(select(Game).where(Game.name == game_name)).first()
                if not game:
                    await progress_queue.put(
                        {"error": f"Game '{game_name}' not found", "status": "failed"}
                    )
                    return

                setting = session.exec(
                    select(AppSetting).where(AppSetting.key == "nexus_api_key")
                ).first()
                if not setting or not setting.value:
                    await progress_queue.put(
                        {"error": "Nexus API key not configured", "status": "failed"}
                    )
                    return

                def progress_cb(job_id: int, downloaded: int, total: int) -> None:
                    pct = round(downloaded / total * 100, 1) if total > 0 else 0.0
                    asyncio.get_event_loop().call_soon_threadsafe(
                        progress_queue.put_nowait,
                        {
                            "job_id": job_id,
                            "status": "downloading",
                            "progress_bytes": downloaded,
                            "total_bytes": total,
                            "percent": pct,
                        },
                    )

                job = await download_service.start_download(
                    game=game,
                    nexus_mod_id=body.nexus_mod_id,
                    nexus_file_id=body.nexus_file_id,
                    api_key=setting.value,
                    session=session,
                    nxm_key=body.nxm_key,
                    nxm_expires=body.nxm_expires,
                    progress_callback=progress_cb,
                )
                await progress_queue.put(
                    {
                        "job_id": job.id,
                        "status": job.status,
                        "progress_bytes": job.progress_bytes,
                        "total_bytes": job.total_bytes,
                        "percent": 100.0 if job.status == "completed" else 0.0,
                        "file_name": job.file_name,
                        "error": job.error,
                    }
                )
        except Exception as e:
            logger.exception("SSE download failed for game '%s'", game_name)
            await progress_queue.put({"error": str(e)[:500], "status": "failed"})
        finally:
            await progress_queue.put(None)

    task = asyncio.create_task(run_download())

    async def event_stream():
        try:
            while True:
                item = await progress_queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
