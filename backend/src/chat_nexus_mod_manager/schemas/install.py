from datetime import datetime

from pydantic import BaseModel


class InstallRequest(BaseModel):
    archive_filename: str
    skip_conflicts: list[str] = []


class InstallResult(BaseModel):
    installed_mod_id: int
    name: str
    files_extracted: int
    files_skipped: int
    files_overwritten: int


class InstalledModOut(BaseModel):
    id: int
    name: str
    source_archive: str
    nexus_mod_id: int | None
    installed_version: str
    disabled: bool
    installed_at: datetime
    file_count: int
    mod_group_id: int | None = None


class UninstallResult(BaseModel):
    files_deleted: int
    directories_removed: int


class ToggleResult(BaseModel):
    disabled: bool
    files_affected: int


class FileConflict(BaseModel):
    file_path: str
    owning_mod_id: int
    owning_mod_name: str


class ConflictCheckResult(BaseModel):
    archive_filename: str
    total_files: int
    conflicts: list[FileConflict]


class AvailableArchive(BaseModel):
    filename: str
    size: int
    nexus_mod_id: int | None = None
    parsed_name: str = ""
    parsed_version: str | None = None
