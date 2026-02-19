from pydantic import BaseModel


class SettingOut(BaseModel):
    key: str
    value: str


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


class PCSpecsOut(BaseModel):
    cpu: str
    gpu: str
    ram_gb: float
    vram_gb: float
    storage_type: str
    os_version: str
    resolution: str
