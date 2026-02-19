from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class DownloadJob(SQLModel, table=True):
    __tablename__ = "download_jobs"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    nexus_mod_id: int
    nexus_file_id: int
    file_name: str = ""
    status: str = "pending"  # pending | downloading | completed | failed | cancelled
    progress_bytes: int = 0
    total_bytes: int = 0
    error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
