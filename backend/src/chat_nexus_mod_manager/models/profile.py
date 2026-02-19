from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from chat_nexus_mod_manager.models.install import InstalledMod


class Profile(SQLModel, table=True):
    __tablename__ = "profiles"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    entries: list["ProfileEntry"] = Relationship(
        back_populates="profile",
        cascade_delete=True,
    )


class ProfileEntry(SQLModel, table=True):
    __tablename__ = "profile_entries"

    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profiles.id", index=True)
    installed_mod_id: int = Field(foreign_key="installed_mods.id")
    enabled: bool = True

    profile: Optional["Profile"] = Relationship(back_populates="entries")
    installed_mod: Optional["InstalledMod"] = Relationship()
