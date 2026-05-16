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


class PreflightReport(BaseModel):
    ok: bool = True
    reasons: list[str] = Field(default_factory=list)
    game_running: bool = False
    hardlink_supported: bool = True
    same_volume: bool = True
    free_disk_bytes: int = 0


class RedmodDeployResult(BaseModel):
    """Result of invoking `redMod.exe deploy` after a VFS deploy.

    REDmods under `mods/<name>/` only load if their cache in `r6/cache/modded/`
    is rebuilt by the REDmod compiler.  This struct surfaces whether the compile
    ran, succeeded, or was intentionally skipped (no binary present, or no REDmods
    enabled) so the UI can show "Deploy complete + REDmod compiled" or
    "Deploy ok but REDmod compile failed: <stderr>".
    """

    ran: bool = False
    success: bool = False
    skipped_reason: str = ""
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""


class DeployReport(BaseModel):
    total: int
    done: int
    failed: int
    skipped_existing: int = 0  # already correctly linked, skipped by plan_deploy
    results: list[DeployOpResult] = Field(default_factory=list)
    preflight: PreflightReport | None = None  # populated when pre-flight refuses
    redmod: RedmodDeployResult | None = None  # set when redmod.exe was attempted

    @property
    def is_clean(self) -> bool:
        return self.failed == 0 and (self.preflight is None or self.preflight.ok)


class DriftReport(BaseModel):
    total: int
    linked: int
    missing: int
    foreign: int  # file exists at dst but is not our link
    by_mod: dict[int, dict[str, int]] = Field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return self.missing == 0 and self.foreign == 0


class MigrationReport(BaseModel):
    """Result of `migrate_to_vfs` — counts of mods/files migrated + any errors."""

    migrated_mods: int = 0
    migrated_files: int = 0
    skipped_files: int = 0
    errors: list[str] = Field(default_factory=list)


class UntrackedFilesResponse(BaseModel):
    """Response model for the untracked-files endpoint."""

    files: list[str] = Field(default_factory=list)
