from datetime import datetime

from pydantic import BaseModel


class ProfileCreate(BaseModel):
    name: str


class ProfileModOut(BaseModel):
    installed_mod_id: int
    name: str
    enabled: bool


class ProfileOut(BaseModel):
    id: int
    name: str
    game_id: int
    created_at: datetime
    mod_count: int
    mods: list[ProfileModOut] = []


class ProfileExportMod(BaseModel):
    name: str
    nexus_mod_id: int | None = None
    version: str = ""
    source_archive: str = ""


class ProfileExport(BaseModel):
    type: str = "cnmm_modlist"
    version: str = "1.0"
    profile_name: str
    game_name: str = ""
    exported_at: datetime
    mod_count: int
    mods: list[ProfileExportMod]


class ProfileImport(BaseModel):
    type: str = "cnmm_modlist"
    version: str = "1.0"
    profile_name: str
    game_name: str = ""
    exported_at: datetime | None = None
    mod_count: int = 0
    mods: list[ProfileExportMod] = []
