from datetime import UTC, datetime

from sqlmodel import Field, Relationship, SQLModel


class InstalledMod(SQLModel, table=True):
    __tablename__ = "installed_mods"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    name: str = Field(index=True)
    source_archive: str = ""
    nexus_mod_id: int | None = None
    nexus_file_id: int | None = None
    upload_timestamp: int | None = None
    installed_version: str = ""
    disabled: bool = False
    installed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mod_group_id: int | None = Field(default=None, foreign_key="mod_groups.id")

    files: list["InstalledModFile"] = Relationship(
        back_populates="installed_mod",
        cascade_delete=True,
    )


class InstalledModFile(SQLModel, table=True):
    __tablename__ = "installed_mod_files"

    id: int | None = Field(default=None, primary_key=True)
    installed_mod_id: int = Field(foreign_key="installed_mods.id", index=True)
    relative_path: str = Field(index=True)

    installed_mod: InstalledMod | None = Relationship(back_populates="files")
