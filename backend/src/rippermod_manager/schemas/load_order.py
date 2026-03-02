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
    loser_mod_ids: list[int]


class PreferModResult(BaseModel):
    success: bool
    message: str
    preferences_added: int = 0
    modlist_entries: int = 0
    dry_run: bool = False


class LegacyPreferModResult(BaseModel):
    """Kept for backward compatibility with the rename-based approach."""

    success: bool
    renames: list[RenameAction]
    dry_run: bool
    message: str
    rollback_performed: bool = False


class ModlistGroupEntry(BaseModel):
    position: int
    mod_id: int | None
    mod_name: str
    archive_filenames: list[str]
    archive_count: int
    is_unmanaged: bool
    has_user_preference: bool


class PreferenceOut(BaseModel):
    id: int
    winner_mod_id: int
    winner_mod_name: str
    loser_mod_id: int
    loser_mod_name: str


class ModlistViewResult(BaseModel):
    game_name: str
    groups: list[ModlistGroupEntry]
    preferences: list[PreferenceOut]
    total_archives: int
    total_groups: int
    total_preferences: int
    modlist_active: bool
    modlist_path: str


class RemovePreferenceResult(BaseModel):
    success: bool
    message: str
    modlist_entries: int


class ResetPreferencesResult(BaseModel):
    removed_count: int
    modlist_entries: int
    message: str
