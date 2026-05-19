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
    # Until artifact parsing lands, all mods sit in phase 0 (single batch).
    phase: int = 0
    # Pre-recorded FOMOD wizard answers from the collection author. Keys are
    # the step / group / plugin *names* (case-sensitive) the user picked.
    # ``None`` or empty -> install only the FOMOD's required files.
    # See services/fomod_choice_resolver.py for translation to indices.
    fomod_choices: dict[str, dict[str, list[str]]] | None = None


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
    # Re-install path: when True and the row already exists, the existing
    # install is uninstalled (cascade through child mods) before the new
    # revision is downloaded + installed. Powers the "Update to rev N"
    # button in :class:`InstalledCollectionsSection`.
    force_reinstall: bool = False


class CollectionStatusOut(BaseModel):
    """Snapshot of an InstalledCollection plus computed progress."""

    id: int
    game_id: int
    slug: str
    revision_number: int
    # The newest revisionNumber the last update-check observed on Nexus.
    # ``None`` when no check has run yet; the UI compares against
    # ``revision_number`` to render an "Update available" pill.
    latest_known_revision_number: int | None
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

    phase: str  # download | awaiting_nxm | install | deploy | done | error
    message: str
    percent: int  # 0-100, derived from completed/failed/skipped vs total
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
    current_mod: str = ""
    status: str = ""  # mirrors InstalledCollection.status when meaningful
    # ``awaiting_nxm`` events carry the Nexus identifiers + page URL so the
    # free-tier dialog can open the right mod page and the user's NXM click
    # gets routed back to the right orchestrator. Empty for every other
    # phase -- the UI keys on ``phase === "awaiting_nxm"``.
    mod_id: int | None = None
    file_id: int | None = None
    mod_page_url: str = ""


class UninstallCollectionOut(BaseModel):
    """Counts returned by ``DELETE /api/v1/collections/{id}``."""

    removed_mods: int
    failed_mods: int


class CollectionSkipNxmRequest(BaseModel):
    """Body for ``POST /collections/{id}/skip-pending-nxm``.

    Identifies which mod of an in-flight free-tier install the user wants
    to skip. The orchestrator can only be blocked on one (mod, file) at a
    time, but the client provides the pair explicitly so the request is
    self-describing in logs / replay.
    """

    nexus_mod_id: int
    nexus_file_id: int


class CollectionActionResult(BaseModel):
    """Generic shape for skip / cancel endpoints.

    ``ok`` is ``True`` when the requested action found an active state to
    act on (a registered NXM wait, a running orchestrator). ``ok=False``
    means the request was a no-op (no waiter / no task), which is fine and
    not treated as an error -- the UI just refreshes the install status.
    """

    ok: bool
    message: str = ""


class CollectionUpdateOut(BaseModel):
    """One entry in the ``POST /check-updates`` response.

    Returned for every :class:`InstalledCollection` the check considered.
    ``error`` is populated when the Nexus lookup for that specific
    collection failed (e.g. slug no longer published) -- the rest of the
    batch still completes so a single failure does not poison the run.
    """

    collection_id: int
    slug: str
    current_revision_number: int
    latest_revision_number: int | None
    has_update: bool
    error: str = ""
