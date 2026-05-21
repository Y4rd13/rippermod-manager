from datetime import datetime

from pydantic import BaseModel


class ActivityLogOut(BaseModel):
    id: int
    action: str
    target: str
    detail: str
    status: str
    created_at: datetime
