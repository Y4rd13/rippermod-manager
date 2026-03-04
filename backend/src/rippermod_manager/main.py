import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import rippermod_manager.models  # noqa: F401 — register all models with SQLModel
from rippermod_manager.config import settings
from rippermod_manager.database import create_db_and_tables
from rippermod_manager.routers import api_router


def _configure_logging() -> None:
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "rippermod.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stderr), file_handler],
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
    try:
        from rippermod_manager.services.download_service import (
            shutdown as shutdown_downloads,
        )

        await shutdown_downloads()
    except Exception:
        logger.exception("Failed to shutdown downloads")
    try:
        from rippermod_manager.database import engine

        engine.dispose()
        logger.info("Database engine disposed")
    except Exception:
        logger.exception("Failed to dispose database engine")
    try:
        from rippermod_manager.vector.store import release_client

        release_client()
    except Exception:
        logger.exception("Failed to release ChromaDB client")
    logger.info("Shutdown complete")


app = FastAPI(
    title="RipperMod Manager",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/health/deep")
async def health_deep() -> dict[str, Any]:
    from starlette.responses import JSONResponse

    checks: dict[str, str] = {}
    all_ok = True

    # DB read check
    try:
        from rippermod_manager.database import engine

        with engine.connect() as conn:
            from sqlmodel import text

            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        all_ok = False

    # ChromaDB heartbeat
    try:
        from rippermod_manager.vector.store import get_chroma_client

        client = get_chroma_client()
        client.heartbeat()
        checks["chromadb"] = "ok"
    except Exception as exc:
        checks["chromadb"] = f"error: {exc}"
        all_ok = False

    # Data dir writability
    try:
        probe = settings.data_dir / ".health_probe"
        probe.write_text("ok")
        probe.unlink()
        checks["data_dir"] = "ok"
    except Exception as exc:
        checks["data_dir"] = f"error: {exc}"
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        content={"status": "healthy" if all_ok else "degraded", "checks": checks},
        status_code=status_code,
    )
