import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import chat_nexus_mod_manager.models  # noqa: F401 — register all models with SQLModel
from chat_nexus_mod_manager.database import create_db_and_tables
from chat_nexus_mod_manager.routers import api_router


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr)],
        force=True,
    )
    for name in ("httpx", "httpcore", "chromadb", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


_configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    logger.info("Application started")
    yield
    logger.info("Shutting down...")
    from chat_nexus_mod_manager.services.download_service import shutdown as shutdown_downloads

    await shutdown_downloads()
    from chat_nexus_mod_manager.database import engine

    engine.dispose()
    logger.info("Database engine disposed")
    import chat_nexus_mod_manager.vector.store as _store

    if _store._client is not None:
        _store._client = None
        logger.info("ChromaDB client released")
    logger.info("Shutdown complete")


app = FastAPI(
    title="Chat Nexus Mod Manager",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "https://tauri.localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
