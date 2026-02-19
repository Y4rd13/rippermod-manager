from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel


class ModGroup(SQLModel, table=True):
    __tablename__ = "mod_groups"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    display_name: str
    confidence: float = 0.0
    scan_timestamp: datetime = Field(default_factory=datetime.utcnow)
    scanner_version: str = "1.0"

    files: list["ModFile"] = Relationship(back_populates="mod_group")
    aliases: list["ModGroupAlias"] = Relationship(back_populates="mod_group")


class ModGroupAlias(SQLModel, table=True):
    __tablename__ = "mod_group_aliases"

    id: int | None = Field(default=None, primary_key=True)
    mod_group_id: int = Field(foreign_key="mod_groups.id", index=True)
    alias: str

    mod_group: ModGroup | None = Relationship(back_populates="aliases")


class ModFile(SQLModel, table=True):
    __tablename__ = "mod_files"

    id: int | None = Field(default=None, primary_key=True)
    mod_group_id: int | None = Field(default=None, foreign_key="mod_groups.id", index=True)
    file_path: str = Field(unique=True)
    filename: str
    file_hash: str = ""
    file_size: int = 0
    source_folder: str = ""

    mod_group: ModGroup | None = Relationship(back_populates="files")
