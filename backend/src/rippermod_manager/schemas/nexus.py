from datetime import datetime

from pydantic import BaseModel


class NexusKeyResult(BaseModel):
    valid: bool
    username: str = ""
    is_premium: bool = False
    error: str = ""


class NexusDownloadOut(BaseModel):
    id: int
    nexus_mod_id: int
    mod_name: str
    file_name: str
    version: str
    category: str
    downloaded_at: datetime | None
    nexus_url: str


class NexusDownloadBrief(BaseModel):
    nexus_mod_id: int
    mod_name: str
    version: str
    nexus_url: str


class NexusSyncResult(BaseModel):
    tracked_mods: int
    endorsed_mods: int
    total_stored: int


class NexusModMetaOut(BaseModel):
    nexus_mod_id: int
    name: str
    summary: str
    author: str
    version: str
    updated_at: datetime | None
    endorsement_count: int
    category: str


class NexusModEnrichedOut(BaseModel):
    id: int
    nexus_mod_id: int
    mod_name: str
    file_name: str
    version: str
    category: str
    downloaded_at: datetime | None
    nexus_url: str
    is_tracked: bool
    is_endorsed: bool
    author: str = ""
    summary: str = ""
    endorsement_count: int = 0
    picture_url: str = ""
    updated_at: datetime | None = None


class ModActionResult(BaseModel):
    success: bool
    is_endorsed: bool | None = None
    is_tracked: bool | None = None


class ModRequirementOut(BaseModel):
    nexus_mod_id: int
    required_mod_id: int | None = None
    mod_name: str = ""
    url: str = ""
    notes: str = ""
    is_external: bool = False


class DlcRequirementOut(BaseModel):
    expansion_name: str = ""
    expansion_id: str | None = None
    notes: str = ""


class ModSummaryOut(BaseModel):
    nexus_mod_id: int
    name: str
    author: str | None = None
    version: str | None = None
    category: str | None = None
    picture_url: str = ""
    nexus_url: str
    is_tracked: bool = False
    is_endorsed: bool = False
    requirements: list[ModRequirementOut] = []
    dlc_requirements: list[DlcRequirementOut] = []


class SSOStartResult(BaseModel):
    uuid: str
    authorize_url: str


class SSOPollResult(BaseModel):
    status: str
    result: NexusKeyResult | None = None
    error: str = ""
