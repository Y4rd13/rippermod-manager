from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import chat_nexus_mod_manager.models  # noqa: F401 — register all models with SQLModel
from chat_nexus_mod_manager.database import create_db_and_tables
from chat_nexus_mod_manager.routers import api_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    yield


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
