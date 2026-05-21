from fastapi import APIRouter

from rippermod_manager.routers.activity import router as activity_router
from rippermod_manager.routers.collections import router as collections_router
from rippermod_manager.routers.conflicts import router as conflicts_router
from rippermod_manager.routers.downloads import router as downloads_router
from rippermod_manager.routers.fomod import router as fomod_router
from rippermod_manager.routers.games import router as games_router
from rippermod_manager.routers.install import router as install_router
from rippermod_manager.routers.load_order import router as load_order_router
from rippermod_manager.routers.mods import router as mods_router
from rippermod_manager.routers.nexus import router as nexus_router
from rippermod_manager.routers.onboarding import router as onboarding_router
from rippermod_manager.routers.profiles import router as profiles_router
from rippermod_manager.routers.settings import router as settings_router
from rippermod_manager.routers.trending import router as trending_router
from rippermod_manager.routers.updates import router as updates_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(games_router)
api_router.include_router(mods_router)
api_router.include_router(install_router)
api_router.include_router(load_order_router)
api_router.include_router(profiles_router)
api_router.include_router(nexus_router)
api_router.include_router(settings_router)
api_router.include_router(conflicts_router)
api_router.include_router(onboarding_router)
api_router.include_router(trending_router)
api_router.include_router(updates_router)
api_router.include_router(downloads_router)
api_router.include_router(fomod_router)
api_router.include_router(collections_router)
api_router.include_router(activity_router)
