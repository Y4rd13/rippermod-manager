"""Models for installed Nexus Collections.

A ``Collection`` on Nexus is a curated, versioned bundle of mods + install
choices authored by another user. ``InstalledCollection`` records the
provenance + state of one such install in the local DB so we can:

- Show "this mod was installed as part of <collection>" in the UI
- Detect when a newer revision is published and offer an update
- Uninstall the whole bundle in one action (cascade through
  ``InstalledMod.installed_collection_id``)
- Resume / restart a partially-completed install after a crash

Per-mod children live on :class:`InstalledMod` via the new
``installed_collection_id`` foreign key (added in the same migration).
``DownloadJob`` also carries the FK so batch progress can be reported.

Tracked in #222 (Phase 1 PR B).
"""

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

#: Lifecycle for an ``InstalledCollection.status`` value. Strings (not enum)
#: to stay consistent with :class:`DownloadJob.status` and survive SQLite
#: schema diffs cleanly.
COLLECTION_STATUS_VALUES = (
    "pending",  # manifest fetched, install not started yet
    "downloading",  # files downloading
    "awaiting_nxm",  # free-tier flow blocked on the user clicking "Download" on Nexus
    "installing",  # files downloaded, archives being installed
    "installed",  # finished successfully
    "partial",  # finished but some mods skipped/failed (user choice or unavailable)
    "failed",  # crashed before completing
    "cancelled",  # user cancelled mid-flow
)


class InstalledCollection(SQLModel, table=True):
    """One installed Nexus Collection (slug + revision) for one game."""

    __tablename__ = "installed_collections"
    # One collection slug can only be installed once per game; re-installing
    # a different revision updates the same row.
    __table_args__ = (UniqueConstraint("game_id", "slug"),)

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)

    slug: str = Field(index=True)
    # Stable Nexus revision UUID — distinct from the human-facing revision
    # number, useful when comparing across re-publishes.
    revision_id: str = Field(default="")
    revision_number: int = 0
    # Populated by the update-check path (latest known on Nexus). When this
    # is greater than ``revision_number`` the UI offers an update.
    latest_known_revision_number: int | None = None

    # Denormalized for the UI so we don't round-trip to Nexus to render the
    # Installed-tab collection group. Refreshed on each install / update.
    collection_name: str = ""
    author_name: str = ""
    summary: str = ""
    tile_image_url: str = ""

    status: str = Field(default="pending", index=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    error: str = ""

    # Counters surfaced in the progress UI (avoid re-aggregating per render).
    total_mods: int = 0
    completed_mods: int = 0
    failed_mods: int = 0
    skipped_mods: int = 0
