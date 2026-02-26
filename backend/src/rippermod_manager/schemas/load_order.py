"""Schemas for archive load-order computation and conflict resolution."""

from pydantic import BaseModel


class LoadOrderEntry(BaseModel):
    position: int
    archive_filename: str
    relative_path: str
    owning_mod_id: int
    owning_mod_name: str
    disabled: bool


class ConflictEvidence(BaseModel):
    file_path: str
    winner_mod_id: int
    winner_mod_name: str
    winner_archive: str
    loser_mod_id: int
    loser_mod_name: str
    loser_archive: str
    reasoning: str


class LoadOrderResult(BaseModel):
    game_name: str
    total_archives: int
    load_order: list[LoadOrderEntry]
    conflicts: list[ConflictEvidence]


class RenameAction(BaseModel):
    old_relative_path: str
    new_relative_path: str
    old_filename: str
    new_filename: str
    owning_mod_id: int
    owning_mod_name: str


class PreferModRequest(BaseModel):
    winner_mod_id: int
    loser_mod_id: int


class PreferModResult(BaseModel):
    success: bool
    renames: list[RenameAction]
    dry_run: bool
    message: str
    rollback_performed: bool = False
