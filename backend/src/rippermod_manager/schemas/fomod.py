"""Pydantic schemas for FOMOD wizard API endpoints."""

from pydantic import BaseModel


class FomodFileMapping(BaseModel):
    source: str
    destination: str
    priority: int
    is_folder: bool


class FomodFlagSetter(BaseModel):
    name: str
    value: str


class FomodTypeDescriptor(BaseModel):
    default_type: str


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
