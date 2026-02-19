from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CNMM_",
        extra="ignore",
    )

    db_path: Path = Path("data/cnmm.db")
    nexus_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    chroma_path: Path = Path("data/chroma")
    host: str = "127.0.0.1"
    port: int = 8425


settings = Settings()
