from datetime import datetime

from pydantic import BaseModel


class ModFileOut(BaseModel):
    id: int
    file_path: str
    filename: str
    file_hash: str
    file_size: int
    source_folder: str


class ModGroupOut(BaseModel):
    id: int
    game_id: int
    display_name: str
    confidence: float
    files: list[ModFileOut] = []
    nexus_match: "CorrelationBrief | None" = None
    earliest_file_mtime: int | None = None


class CorrelationBrief(BaseModel):
    nexus_mod_id: int
    mod_name: str
    score: float
    method: str
    confirmed: bool
    author: str = ""
    summary: str = ""
    version: str = ""
    endorsement_count: int = 0
    category: str = ""
    picture_url: str = ""
    nexus_url: str = ""
    updated_at: datetime | None = None


class ScanResult(BaseModel):
    files_found: int
    groups_created: int
    new_files: int


class CorrelateResult(BaseModel):
    total_groups: int
    matched: int
    unmatched: int


class EnrichResult(BaseModel):
    ids_found: int
    ids_new: int
    ids_failed: int


class ArchiveMatchResult(BaseModel):
    archives_scanned: int
    matched: int
    unmatched: int


class WebSearchResult(BaseModel):
    searched: int
    matched: int
    unmatched: int


class CorrelationReassign(BaseModel):
    nexus_mod_id: int


class ScanStreamRequest(BaseModel):
    ai_search: bool = False
    ai_search_model: str | None = None
    ai_search_effort: str | None = None


ModGroupOut.model_rebuild()
