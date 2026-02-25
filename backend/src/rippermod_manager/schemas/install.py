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
    nexus_updated_at: datetime | None = None
    nexus_name: str | None = None
    summary: str | None = None
    author: str | None = None
    endorsement_count: int | None = None
    picture_url: str | None = None
    category: str | None = None
    last_downloaded_at: datetime | None = None
    nexus_url: str | None = None


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
    is_fomod: bool = False


class AvailableArchive(BaseModel):
    filename: str
    size: int
    nexus_mod_id: int | None = None
    parsed_name: str = ""
    parsed_version: str | None = None
    is_installed: bool = False
    installed_mod_id: int | None = None
    last_downloaded_at: datetime | None = None


class ArchiveDeleteResult(BaseModel):
    filename: str
    deleted: bool
    message: str


class OrphanCleanupResult(BaseModel):
    deleted_count: int
    freed_bytes: int
    deleted_files: list[str]
