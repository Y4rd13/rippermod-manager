"""Response schema for the framework mod monitor."""

from typing import Literal

from pydantic import BaseModel

ManagerStatus = Literal["active", "deploy_pending", "disabled", "not_installed"]


class FrameworkStatus(BaseModel):
    key: str
    name: str
    installed: bool  # marker present in the game dir (== manager_status "active")
    manager_status: ManagerStatus = "not_installed"
    version: str | None = None
    version_known: bool = False
    latest_version: str | None = None
    latest_is_cached: bool = False  # latest_version came from the offline cache
    outdated: bool = False
    nexus_url: str
