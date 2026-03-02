from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class LoadOrderPreference(SQLModel, table=True):
    __tablename__ = "load_order_preferences"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    winner_mod_id: int = Field(foreign_key="installed_mods.id")
    loser_mod_id: int = Field(foreign_key="installed_mods.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
