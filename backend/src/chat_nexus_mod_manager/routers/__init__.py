from fastapi import APIRouter

from chat_nexus_mod_manager.routers.chat import router as chat_router
from chat_nexus_mod_manager.routers.downloads import router as downloads_router
from chat_nexus_mod_manager.routers.games import router as games_router
from chat_nexus_mod_manager.routers.install import router as install_router
from chat_nexus_mod_manager.routers.mods import router as mods_router
from chat_nexus_mod_manager.routers.nexus import router as nexus_router
from chat_nexus_mod_manager.routers.onboarding import router as onboarding_router
from chat_nexus_mod_manager.routers.profiles import router as profiles_router
from chat_nexus_mod_manager.routers.settings import router as settings_router
from chat_nexus_mod_manager.routers.trending import router as trending_router
from chat_nexus_mod_manager.routers.updates import router as updates_router
from chat_nexus_mod_manager.routers.vector import router as vector_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(games_router)
api_router.include_router(mods_router)
api_router.include_router(install_router)
api_router.include_router(profiles_router)
api_router.include_router(nexus_router)
api_router.include_router(settings_router)
api_router.include_router(chat_router)
api_router.include_router(onboarding_router)
api_router.include_router(trending_router)
api_router.include_router(updates_router)
api_router.include_router(downloads_router)
api_router.include_router(vector_router)
