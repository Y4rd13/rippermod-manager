"""Response schema for the mod error reader."""

from pydantic import BaseModel


class LogError(BaseModel):
    source: str  # which framework log it came from (RED4ext, CET, redscript, ...)
    level: str  # "error" | "warning"
    timestamp: str  # raw timestamp as it appears in the log (formats vary)
    message: str
    mod_name: str | None = None  # reserved for attribution (not populated in v1)
