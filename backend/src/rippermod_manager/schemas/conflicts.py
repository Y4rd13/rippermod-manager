from pydantic import BaseModel


class ConflictGraphNode(BaseModel):
    id: str
    label: str
    source_type: str
    file_count: int
    conflict_count: int
    disabled: bool = False
    nexus_mod_id: int | None = None
    picture_url: str | None = None


class ConflictGraphEdge(BaseModel):
    source: str
    target: str
    shared_files: list[str]
    weight: int


class ConflictGraphResult(BaseModel):
    nodes: list[ConflictGraphNode]
    edges: list[ConflictGraphEdge]
    total_conflicts: int
