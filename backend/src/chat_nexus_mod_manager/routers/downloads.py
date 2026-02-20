import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.settings import AppSetting
from chat_nexus_mod_manager.routers.deps import get_game_or_404
from chat_nexus_mod_manager.schemas.download import (
    DownloadFromModRequest,
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

    job = await download_service.create_and_start_download(
        game=game,
        nexus_mod_id=body.nexus_mod_id,
        nexus_file_id=body.nexus_file_id,
        api_key=api_key,
        session=session,
        nxm_key=body.nxm_key,
        nxm_expires=body.nxm_expires,
    )

    return DownloadStartResult(job=_job_to_out(job), requires_nxm=False)


@router.post("/from-mod", response_model=DownloadStartResult)
async def start_download_from_mod(
    game_name: str,
    body: DownloadFromModRequest,
    session: Session = Depends(get_session),
) -> DownloadStartResult:
    """Resolve the main file for a mod and start downloading it."""
    game = get_game_or_404(game_name, session)
    api_key = _get_api_key(session)

    from chat_nexus_mod_manager.nexus.client import NexusClient

    async with NexusClient(api_key) as client:
        key_result = await client.validate_key()
        files_resp = await client.get_mod_files(game.domain_name, body.nexus_mod_id)

    nexus_files = files_resp.get("files", [])
    if not nexus_files:
        raise HTTPException(404, "No files found for this mod")

    # Prefer main files (category_id == 1), fallback to latest file
    main_files = [f for f in nexus_files if f.get("category_id") == 1]
    target = main_files[-1] if main_files else nexus_files[-1]
    nexus_file_id = target["file_id"]

    if not key_result.is_premium:
        from chat_nexus_mod_manager.models.download import DownloadJob

        job = DownloadJob(
            game_id=game.id,  # type: ignore[arg-type]
            nexus_mod_id=body.nexus_mod_id,
            nexus_file_id=nexus_file_id,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return DownloadStartResult(job=_job_to_out(job), requires_nxm=True)

    job = await download_service.create_and_start_download(
        game=game,
        nexus_mod_id=body.nexus_mod_id,
        nexus_file_id=nexus_file_id,
        api_key=api_key,
        session=session,
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
