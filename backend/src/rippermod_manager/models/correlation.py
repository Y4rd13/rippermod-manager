from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RejectedCorrelation(SQLModel, table=True):
    """A (mod group, Nexus mod) pair the user rejected; no matcher re-creates it."""

    __tablename__ = "rejected_correlations"
    __table_args__ = (UniqueConstraint("mod_group_id", "nexus_mod_id"),)

    id: int | None = Field(default=None, primary_key=True)
    mod_group_id: int = Field(foreign_key="mod_groups.id", index=True)
    nexus_mod_id: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
