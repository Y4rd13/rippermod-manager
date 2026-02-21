from datetime import datetime

from pydantic import BaseModel, computed_field


class DownloadRequest(BaseModel):
    nexus_mod_id: int
    nexus_file_id: int
    nxm_key: str | None = None
    nxm_expires: int | None = None


class DownloadFromModRequest(BaseModel):
    nexus_mod_id: int


class DownloadJobOut(BaseModel):
    id: int
    nexus_mod_id: int
    nexus_file_id: int
    file_name: str
    status: str
    progress_bytes: int
    total_bytes: int
    error: str
    created_at: datetime
    completed_at: datetime | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return round(self.progress_bytes / self.total_bytes * 100, 1)


class DownloadStartResult(BaseModel):
    job: DownloadJobOut | None = None
    requires_nxm: bool
