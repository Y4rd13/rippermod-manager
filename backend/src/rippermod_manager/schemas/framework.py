"""Response schema for the framework mod monitor."""

from pydantic import BaseModel


class FrameworkStatus(BaseModel):
    key: str
    name: str
    installed: bool
    version: str | None = None
    version_known: bool = False
    latest_version: str | None = None
    outdated: bool = False
    nexus_url: str
