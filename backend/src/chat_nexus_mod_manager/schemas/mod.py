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


class CorrelationBrief(BaseModel):
    nexus_mod_id: int
    mod_name: str
    score: float
    method: str
    confirmed: bool


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


ModGroupOut.model_rebuild()
