import logging

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session

from rippermod_manager.database import get_session
from rippermod_manager.matching.filename_parser import is_newer_version
from rippermod_manager.nexus.graphql_client import NexusGraphQLClient
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.framework import FrameworkStatus
from rippermod_manager.services import framework_service as svc
from rippermod_manager.services.settings_helpers import get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games/{game_name}/frameworks", tags=["frameworks"])


@router.get("/", response_model=list[FrameworkStatus])
async def get_frameworks(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[FrameworkStatus]:
    """Status of the core Cyberpunk modding frameworks: installed, on-disk
    version, and — when a Nexus key is configured and reachable — whether a
    newer version is available. The Nexus lookup is best-effort."""
    game = get_game_or_404(game_name, session)
    # Blocking pefile / filesystem detection runs off the event loop.
    detected = await run_in_threadpool(svc.detect_frameworks, game.install_path)

    latest: dict[int, str] = {}
    api_key = get_setting(session, "nexus_api_key")
    if api_key:
        async with NexusGraphQLClient(api_key) as gql:
            latest = await svc.fetch_latest_versions(
                game.domain_name, gql, [d["nexus_mod_id"] for d in detected]
            )

    report: list[FrameworkStatus] = []
    for d in detected:
        latest_v = latest.get(d["nexus_mod_id"])
        outdated = bool(d["version"] and latest_v and is_newer_version(latest_v, d["version"]))
        report.append(
            FrameworkStatus(
                key=d["key"],
                name=d["name"],
                installed=d["installed"],
                version=d["version"],
                version_known=d["version_known"],
                latest_version=latest_v,
                outdated=outdated,
                nexus_url=f"https://www.nexusmods.com/{game.domain_name}/mods/{d['nexus_mod_id']}",
            )
        )
    return report
