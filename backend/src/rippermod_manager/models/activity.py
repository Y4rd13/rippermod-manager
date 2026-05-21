from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ActivityLog(SQLModel, table=True):
    """Timestamped history of meaningful user actions, scoped per game.

    Append-only and pruned to a per-game cap (see ``services/activity_service``).
    Modeled after ``DeployJournalEntry`` but kept as a separate, durable record
    of what the user changed — not a write-ahead log.
    """

    __tablename__ = "activity_log"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    action: str  # install | uninstall | enable | disable | deploy | undeploy | download
    target: str = Field(default="")  # mod name (or a summary like "5 mods")
    detail: str = Field(default="")  # counts / version / extra context
    status: str = Field(default="success")  # success | failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
