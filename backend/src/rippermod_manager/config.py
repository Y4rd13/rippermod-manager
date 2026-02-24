import os
import sys
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    if env := os.environ.get("RMM_DATA_DIR"):
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "com.rippermod.app"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RMM_",
        extra="ignore",
    )

    data_dir: Path = Path("")
    db_path: Path = Path("")
    chroma_path: Path = Path("")
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    tavily_api_key: str = ""
    host: str = "127.0.0.1"
    port: int = 8425

    @model_validator(mode="after")
    def _resolve_data_paths(self) -> "Settings":
        if self.data_dir == Path(""):
            self.data_dir = _default_data_dir()
        if self.db_path == Path(""):
            self.db_path = self.data_dir / "rmm.db"
        if self.chroma_path == Path(""):
            self.chroma_path = self.data_dir / "chroma"
        return self


settings = Settings()
