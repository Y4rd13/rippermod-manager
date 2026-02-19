from datetime import datetime

from pydantic import BaseModel


class ModPathIn(BaseModel):
    relative_path: str
    description: str = ""
    is_default: bool = True


class GameCreate(BaseModel):
    name: str
    domain_name: str
    install_path: str
    os: str = "windows"
    mod_paths: list[ModPathIn] = []


class ModPathOut(BaseModel):
    id: int
    relative_path: str
    description: str
    is_default: bool


class GameOut(BaseModel):
    id: int
    name: str
    domain_name: str
    install_path: str
    os: str
    created_at: datetime
    updated_at: datetime
    mod_paths: list[ModPathOut] = []


class PathValidationRequest(BaseModel):
    install_path: str


class PathValidation(BaseModel):
    valid: bool
    path: str
    found_exe: bool
    found_mod_dirs: list[str]
    warning: str = ""
