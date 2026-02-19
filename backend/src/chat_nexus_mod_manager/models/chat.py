from datetime import datetime

from sqlmodel import Field, SQLModel


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: int | None = Field(default=None, primary_key=True)
    role: str
    content: str = ""
    tool_calls_json: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
