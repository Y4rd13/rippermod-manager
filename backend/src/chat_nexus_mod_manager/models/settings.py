from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_settings"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str = ""
    encrypted: bool = False


class PCSpecs(SQLModel, table=True):
    __tablename__ = "pc_specs"

    id: int | None = Field(default=None, primary_key=True)
    cpu: str = ""
    gpu: str = ""
    ram_gb: float = 0
    vram_gb: float = 0
    storage_type: str = ""
    os_version: str = ""
    resolution: str = ""
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
