from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ProfileCreate(BaseModel):
    name: str
    description: str = ""


class ProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProfileModOut(BaseModel):
    installed_mod_id: int
    name: str
    enabled: bool


class ProfileOut(BaseModel):
    id: int
    name: str
    game_id: int
    description: str = ""
    created_at: datetime
    last_loaded_at: datetime | None = None
    is_active: bool = False
    is_drifted: bool = False
    mod_count: int
    mods: list[ProfileModOut] = []


# --- Diff / Preview (Feature 1) ---


class ProfileDiffEntry(BaseModel):
    mod_name: str
    installed_mod_id: int | None = None
    action: Literal["enable", "disable", "missing", "unchanged"]


class ProfileDiffOut(BaseModel):
    profile_name: str
    entries: list[ProfileDiffEntry]
    enable_count: int
    disable_count: int
    missing_count: int
    unchanged_count: int


# --- Missing Mods Report (Feature 3) ---


class SkippedMod(BaseModel):
    name: str
    installed_mod_id: int | None = None


class ProfileLoadResult(BaseModel):
    profile: ProfileOut
    skipped_mods: list[SkippedMod] = []
    skipped_count: int = 0


class ProfileImportResult(BaseModel):
    profile: ProfileOut
    matched_count: int = 0
    skipped_mods: list[SkippedMod] = []
    skipped_count: int = 0


# --- Duplicate (Feature 6) ---


class ProfileDuplicateRequest(BaseModel):
    name: str


# --- Compare (Feature 7) ---


class ProfileCompareEntry(BaseModel):
    mod_name: str
    installed_mod_id: int | None = None
    enabled_in_a: bool | None = None
    enabled_in_b: bool | None = None


class ProfileCompareOut(BaseModel):
    profile_a_name: str
    profile_b_name: str
    only_in_a: list[ProfileCompareEntry]
    only_in_b: list[ProfileCompareEntry]
    in_both: list[ProfileCompareEntry]
    only_in_a_count: int
    only_in_b_count: int
    in_both_count: int


class ProfileCompareRequest(BaseModel):
    profile_id_a: int
    profile_id_b: int


# --- Export / Import ---


class ProfileExportMod(BaseModel):
    name: str
    nexus_mod_id: int | None = None
    version: str = ""
    source_archive: str = ""
    enabled: bool = True


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
