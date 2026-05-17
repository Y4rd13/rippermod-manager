from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from rippermod_manager.services.paths import resolve_mods_dir


class ModPathIn(BaseModel):
    relative_path: str
    description: str = ""
    is_default: bool = True


class GameCreate(BaseModel):
    name: str
    domain_name: str
    install_path: str
    mods_dir: str | None = None
    os: str = "windows"
    mod_paths: list[ModPathIn] = []


class GameUpdate(BaseModel):
    mods_dir: str | None = None


class ModPathOut(BaseModel):
    id: int
    relative_path: str
    description: str
    is_default: bool


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain_name: str
    install_path: str
    mods_dir: str | None = None
    resolved_mods_dir: str = ""
    os: str
    created_at: datetime
    updated_at: datetime
    mod_paths: list[ModPathOut] = []

    @model_validator(mode="after")
    def _fill_resolved_mods_dir(self) -> "GameOut":
        if not self.resolved_mods_dir:
            self.resolved_mods_dir = str(resolve_mods_dir(self.install_path, self.mods_dir))
        return self


class GameVersion(BaseModel):
    version: str | None
    exe_path: str


class PathValidationRequest(BaseModel):
    install_path: str
    domain_name: str = "cyberpunk2077"


class PathValidation(BaseModel):
    valid: bool
    path: str
    found_exe: bool
    found_mod_dirs: list[str]
    warning: str = ""
