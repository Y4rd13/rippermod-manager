from datetime import datetime

from sqlmodel import Field, SQLModel


class NexusDownload(SQLModel, table=True):
    __tablename__ = "nexus_downloads"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    nexus_mod_id: int = Field(index=True)
    mod_name: str = ""
    file_name: str = ""
    file_id: int | None = None
    version: str = ""
    category: str = ""
    downloaded_at: datetime | None = None
    nexus_url: str = ""
    is_tracked: bool = Field(default=False)
    is_endorsed: bool = Field(default=False)


class NexusModMeta(SQLModel, table=True):
    __tablename__ = "nexus_mod_meta"

    id: int | None = Field(default=None, primary_key=True)
    nexus_mod_id: int = Field(index=True, unique=True)
    game_domain: str = ""
    name: str = ""
    summary: str = ""
    description: str = ""
    author: str = ""
    version: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    endorsement_count: int = 0
    mod_downloads: int = 0
    category: str = ""
    picture_url: str = ""


class NexusModFile(SQLModel, table=True):
    __tablename__ = "nexus_mod_files"

    id: int | None = Field(default=None, primary_key=True)
    nexus_mod_id: int = Field(index=True)
    file_id: int = Field(index=True)
    file_name: str = ""
    version: str = ""
    category_id: int | None = None
    uploaded_timestamp: int | None = None
    file_size: int = 0
