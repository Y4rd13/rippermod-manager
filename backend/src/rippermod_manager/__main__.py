"""Entry point for standalone backend process."""

import sys

import uvicorn

from rippermod_manager.config import settings
from rippermod_manager.main import app


def main() -> None:
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
        reload=not getattr(sys, "frozen", False),
    )


if __name__ == "__main__":
    main()
