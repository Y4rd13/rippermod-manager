from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OpKind = Literal["link", "unlink", "junction", "rm_junction"]


class DeployOp(BaseModel):
    operation: OpKind
    src: str  # staging-relative for link/junction; ignored for unlink/rm_junction
    dst: str  # game-relative
    installed_mod_id: int | None = None


class DeployPlan(BaseModel):
    game_id: int
    ops: list[DeployOp] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.ops


class DeployOpResult(BaseModel):
    op: DeployOp
    status: Literal["done", "failed"]
    error: str = ""


class DeployReport(BaseModel):
    total: int
    done: int
    failed: int
    results: list[DeployOpResult] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.failed == 0


class DriftReport(BaseModel):
    total: int
    linked: int
    missing: int
    foreign: int  # file exists at dst but is not our link
    by_mod: dict[int, dict[str, int]] = Field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return self.missing == 0 and self.foreign == 0


class PreflightReport(BaseModel):
    ok: bool = True
    reasons: list[str] = Field(default_factory=list)
    game_running: bool = False
    hardlink_supported: bool = True
    same_volume: bool = True
    free_disk_bytes: int = 0
