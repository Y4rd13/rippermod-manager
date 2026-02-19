from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    game_name: str | None = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    tool_calls_json: str
    created_at: datetime
