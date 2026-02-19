from datetime import datetime

from sqlmodel import Field, SQLModel


class ModNexusCorrelation(SQLModel, table=True):
    __tablename__ = "mod_nexus_correlations"

    id: int | None = Field(default=None, primary_key=True)
    mod_group_id: int = Field(foreign_key="mod_groups.id", index=True)
    nexus_download_id: int = Field(foreign_key="nexus_downloads.id", index=True)
    score: float = 0.0
    method: str = ""
    reasoning: str = ""
    confirmed_by_user: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
