from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel


class Game(SQLModel, table=True):
    __tablename__ = "games"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    domain_name: str = Field(index=True)
    install_path: str
    os: str = "windows"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    mod_paths: list["GameModPath"] = Relationship(back_populates="game")


class GameModPath(SQLModel, table=True):
    __tablename__ = "game_mod_paths"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    relative_path: str
    description: str = ""
    is_default: bool = True

    game: Game | None = Relationship(back_populates="mod_paths")
