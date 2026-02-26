"""Schemas for redscript static-analysis conflict detection."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class RedscriptAnnotationType(StrEnum):
    REPLACE_METHOD = "replaceMethod"
    REPLACE_GLOBAL = "replaceGlobal"
    WRAP_METHOD = "wrapMethod"


class RedscriptTarget(BaseModel):
    """A single parsed annotation target from a .reds file."""

    annotation_type: RedscriptAnnotationType
    class_name: str | None
    func_name: str
    param_types: list[str]
    return_type: str
    conflict_key: str


class RedscriptModEntry(BaseModel):
    """A mod that touches a particular redscript target."""

    installed_mod_id: int
    installed_mod_name: str
    file_path: str
    annotation_type: RedscriptAnnotationType
    line_number: int


class RedscriptConflict(BaseModel):
    """A conflict where >=2 mods replace the same target."""

    conflict_key: str
    target_class: str | None
    target_func: str
    mods: list[RedscriptModEntry]


class RedscriptWrapInfo(BaseModel):
    """Informational: mods wrapping the same target (compatible, not a conflict)."""

    conflict_key: str
    target_class: str | None
    target_func: str
    mods: list[RedscriptModEntry]


class RedscriptConflictResult(BaseModel):
    """Full result of redscript conflict analysis."""

    total_reds_files: int
    total_targets_found: int
    conflicts: list[RedscriptConflict]
    wraps: list[RedscriptWrapInfo]
