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
