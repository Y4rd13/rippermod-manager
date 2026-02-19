from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]


class ChatRequest(BaseModel):
    message: str
    game_name: str | None = None
    reasoning_effort: ReasoningEffort = "none"


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    tool_calls_json: str
    created_at: datetime
