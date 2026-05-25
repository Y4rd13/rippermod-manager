from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class InstalledMod(SQLModel, table=True):
    __tablename__ = "installed_mods"
    __table_args__ = (UniqueConstraint("game_id", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    name: str = Field(index=True)
    source_archive: str = ""
    nexus_mod_id: int | None = None
    nexus_file_id: int | None = None
    upload_timestamp: int | None = None
    installed_version: str = ""
    disabled: bool = False
    conflict_dismissed: bool = False
    installed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mod_group_id: int | None = Field(default=None, foreign_key="mod_groups.id")
    staging_dir: str = Field(default="")
    deployed: bool = Field(default=False)
    deploy_drift: bool = Field(default=False)
    # Collection provenance — set when this mod was installed as part of an
    # ``InstalledCollection`` bundle (#222). ``None`` for stand-alone installs.
    installed_collection_id: int | None = Field(
        default=None, foreign_key="installed_collections.id", index=True
    )
    # The collection author's install-order bucket for this mod (mirrors
    # Vortex's ``phase`` field on ``ICollectionMod``). Phase N must finish
    # before phase N+1 starts.
    collection_phase: int = 0
    # Was this mod marked optional in the collection manifest? Surfaced in
    # the preview dialog so users can deselect optionals before install.
    is_optional: bool = False

    files: list["InstalledModFile"] = Relationship(
        back_populates="installed_mod",
        cascade_delete=True,
    )


class InstalledModFile(SQLModel, table=True):
    __tablename__ = "installed_mod_files"

    id: int | None = Field(default=None, primary_key=True)
    installed_mod_id: int = Field(foreign_key="installed_mods.id", index=True)
    relative_path: str = Field(index=True)
    source_path: str = Field(default="")
    link_kind: str = Field(default="hardlink")  # hardlink | junction | copy

    installed_mod: InstalledMod | None = Relationship(back_populates="files")


class ArchiveNexusLink(SQLModel, table=True):
    __tablename__ = "archive_nexus_links"
    __table_args__ = (UniqueConstraint("game_id", "filename"),)

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    filename: str = Field(index=True)
    nexus_mod_id: int


class DeployJournalEntry(SQLModel, table=True):
    __tablename__ = "deploy_journal"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    operation: str  # link | unlink | junction | rm_junction | adopt
    src: str
    dst: str
    status: str = Field(default="pending")  # pending | done | failed
    error: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
