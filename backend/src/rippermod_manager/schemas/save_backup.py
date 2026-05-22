"""Request/response schemas for the save game backup feature."""

from pydantic import BaseModel


class SaveBackupOut(BaseModel):
    """A single save backup as surfaced to the UI."""

    id: str  # timestamped folder name, also the restore handle
    created_at: str | None = None
    reason: str | None = None
    file_count: int | None = None
    size_bytes: int | None = None


class SaveBackupStatus(BaseModel):
    """Status payload for the Settings card: toggle state, resolved save folder,
    and the list of existing backups (most recent first)."""

    enabled: bool
    save_dir: str
    save_dir_exists: bool
    backups: list[SaveBackupOut]


class RestoreRequest(BaseModel):
    id: str


class SaveBackupActionResult(BaseModel):
    created: bool = False
    restored: bool = False
    backup: SaveBackupOut | None = None
    restored_to: str | None = None
