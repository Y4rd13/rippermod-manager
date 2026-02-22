from datetime import datetime

from pydantic import BaseModel


class NexusKeyValidation(BaseModel):
    api_key: str


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


class TrendingModOut(BaseModel):
    mod_id: int
    name: str
    summary: str = ""
    author: str = ""
    version: str = ""
    picture_url: str = ""
    endorsement_count: int = 0
    mod_downloads: int = 0
    mod_unique_downloads: int = 0
    created_timestamp: int = 0
    updated_timestamp: int = 0
    category_id: int | None = None
    nexus_url: str = ""
    is_installed: bool = False
    is_tracked: bool = False
    is_endorsed: bool = False


class TrendingResult(BaseModel):
    trending: list[TrendingModOut]
    latest_updated: list[TrendingModOut]
    cached: bool


class NexusModFileOut(BaseModel):
    file_id: int
    file_name: str
    version: str
    category_id: int | None
    uploaded_timestamp: int | None
    file_size: int


class ModDetailOut(BaseModel):
    nexus_mod_id: int
    game_domain: str
    name: str
    summary: str
    description: str
    author: str
    version: str
    created_at: datetime | None
    updated_at: datetime | None
    endorsement_count: int
    mod_downloads: int
    category: str
    picture_url: str
    nexus_url: str
    changelogs: dict[str, list[str]]
    files: list[NexusModFileOut]


class SSOStartResult(BaseModel):
    uuid: str
    authorize_url: str


class SSOPollResult(BaseModel):
    status: str
    result: NexusKeyResult | None = None
    error: str = ""
