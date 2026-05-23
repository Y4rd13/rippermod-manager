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
    ids = [d["nexus_mod_id"] for d in detected]

    # Manager state + a cached latest-version baseline let the widget say
    # something useful even offline / without a Nexus key.
    mgr = svc.framework_manager_state(session, game.id)
    cached = svc.cached_latest_versions(session, ids)

    live: dict[int, str] = {}
    api_key = get_setting(session, "nexus_api_key")
    if api_key:
        async with NexusGraphQLClient(api_key) as gql:
            live = await svc.fetch_latest_versions(game.domain_name, gql, ids)

    report: list[FrameworkStatus] = []
    for d in detected:
        mod_id = d["nexus_mod_id"]
        latest_v = live.get(mod_id) or cached.get(mod_id)
        latest_is_cached = latest_v is not None and mod_id not in live
        outdated = bool(d["version"] and latest_v and is_newer_version(latest_v, d["version"]))
        report.append(
            FrameworkStatus(
                key=d["key"],
                name=d["name"],
                installed=d["installed"],
                manager_status=svc.manager_status(d["installed"], mgr.get(mod_id)),
                version=d["version"],
                version_known=d["version_known"],
                latest_version=latest_v,
                latest_is_cached=latest_is_cached,
                outdated=outdated,
                nexus_url=f"https://www.nexusmods.com/{game.domain_name}/mods/{mod_id}",
            )
        )
    return report
