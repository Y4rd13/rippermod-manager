"""Schemas for Nexus Collections install (#222)."""

from datetime import datetime

from pydantic import BaseModel, computed_field


class CollectionModEntry(BaseModel):
    """One mod listed in a Collection revision's manifest."""

    nexus_mod_id: int
    nexus_file_id: int
    name: str
    version: str
    author: str
    summary: str
    size_bytes: int
    picture_url: str
    optional: bool
    # Phase comes from collection.json inside the artifact (Vortex pattern).
    # Until PR D parses that artifact, all mods sit in phase 0 (single batch).
    phase: int = 0


class CollectionPreviewOut(BaseModel):
    """Manifest + collection identity for the install preview dialog."""

    slug: str
    revision_id: str
    revision_number: int
    name: str
    summary: str
    description: str
    author: str
    tile_image_url: str
    endorsements: int
    total_downloads: int
    total_size_bytes: int
    mods: list[CollectionModEntry]


class CollectionInstallRequest(BaseModel):
    """Body for kicking off an install of a (slug, revision) into a game."""

    slug: str
    revision: int
    # Allow the UI to exclude specific optional mods (by nexus_mod_id) without
    # rebuilding the whole manifest server-side.
    skip_mod_ids: list[int] = []
    # When False, every ``optional=True`` mod is also skipped. Default True so
    # the user gets the author-intended bundle unless they opt out.
    include_optional: bool = True


class CollectionStatusOut(BaseModel):
    """Snapshot of an InstalledCollection plus computed progress."""

    id: int
    game_id: int
    slug: str
    revision_number: int
    name: str
    author: str
    summary: str
    tile_image_url: str
    status: str
    total_mods: int
    completed_mods: int
    failed_mods: int
    skipped_mods: int
    started_at: datetime
    finished_at: datetime | None
    error: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def percent(self) -> float:
        """Aggregate progress 0-100, included in API responses.

        Uses ``@computed_field`` so Pydantic v2's ``model_dump_json()``
        serializes it — a plain ``@property`` would be silently dropped
        from the response payload.
        """
        if self.total_mods <= 0:
            return 0.0
        done = self.completed_mods + self.failed_mods + self.skipped_mods
        return round(done / self.total_mods * 100, 1)


class CollectionProgressEvent(BaseModel):
    """One SSE event emitted by the install orchestrator."""

    phase: str  # download | install | deploy | done | error
    message: str
    percent: int  # 0-100, derived from completed/failed/skipped vs total
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
    current_mod: str = ""
    status: str = ""  # mirrors InstalledCollection.status when meaningful
