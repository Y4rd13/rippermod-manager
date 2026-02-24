"""Pydantic schemas for FOMOD wizard API endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FomodFileMapping(BaseModel):
    source: str
    destination: str
    priority: int
    is_folder: bool


class FomodFlagSetter(BaseModel):
    name: str
    value: str


class FomodFlagCondition(BaseModel):
    name: str
    value: str


class FomodFileCondition(BaseModel):
    file: str
    state: Literal["Active", "Inactive", "Missing"]


class FomodCompositeDependency(BaseModel):
    operator: Literal["And", "Or"]
    flag_conditions: list[FomodFlagCondition] = []
    file_conditions: list[FomodFileCondition] = []
    nested: list[FomodCompositeDependency] = []


FomodCompositeDependency.model_rebuild()


class FomodTypeDescriptorPattern(BaseModel):
    dependency: FomodCompositeDependency
    type: str


class FomodTypeDescriptor(BaseModel):
    default_type: str
    patterns: list[FomodTypeDescriptorPattern] = []


class FomodPluginOut(BaseModel):
    name: str
    description: str
    image_path: str
    files: list[FomodFileMapping]
    condition_flags: list[FomodFlagSetter]
    type_descriptor: FomodTypeDescriptor


class FomodGroupOut(BaseModel):
    name: str
    type: str
    plugins: list[FomodPluginOut]


class FomodStepOut(BaseModel):
    name: str
    groups: list[FomodGroupOut]
    visible: FomodCompositeDependency | None = None


class FomodConfigOut(BaseModel):
    module_name: str
    module_image: str
    required_install_files: list[FomodFileMapping]
    steps: list[FomodStepOut]
    has_conditional_installs: bool
    total_steps: int


class FomodInstallRequest(BaseModel):
    archive_filename: str
    mod_name: str
    selections: dict[int, dict[int, list[int]]]
    skip_conflicts: list[str] = []


class FomodPreviewFile(BaseModel):
    game_relative_path: str
    source: str
    priority: int


class FomodPreviewRequest(BaseModel):
    archive_filename: str
    selections: dict[int, dict[int, list[int]]]


class FomodPreviewResult(BaseModel):
    files: list[FomodPreviewFile]
    total_files: int
