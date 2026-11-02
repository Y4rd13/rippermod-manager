"""Decide which Nexus mod ids are on disk, and which are only possible matches.

One place answers "is this Nexus mod installed?" so Health, Conflicts, Archives and the
mod list agree. A mod is on disk when the app manages it (``InstalledMod``) or when a scanned
group is correlated to it with a high enough score or a user confirmation. A lower-scoring
correlation is only a *possible* match: it is shown as such, never counted as installed.
"""

from dataclasses import dataclass, field
from typing import Literal

from sqlmodel import Session, select

from rippermod_manager.matching.filename_parser import parse_mod_filename
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.download import DownloadJob
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import ArchiveNexusLink, InstalledMod
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload

# Correlation score from which an unconfirmed match counts as "on disk".
ON_DISK_MIN_SCORE: float = 0.75

ArchiveStatus = Literal[
    "managed", "not_managed", "possible_match", "other_version", "not_installed", "orphan"
]


@dataclass(frozen=True)
class DiskMatch:
    mod_group_id: int
    nexus_mod_id: int
    score: float
    confirmed: bool
    on_disk: bool


@dataclass
class Presence:
    managed_ids: set[int] = field(default_factory=set)
    matches: dict[int, DiskMatch] = field(default_factory=dict)  # keyed by nexus_mod_id

    def is_on_disk(self, nexus_mod_id: int) -> bool:
        if nexus_mod_id in self.managed_ids:
            return True
        match = self.matches.get(nexus_mod_id)
        return match is not None and match.on_disk

    def possible(self, nexus_mod_id: int) -> DiskMatch | None:
        """The scanned-group match for this id when it is not on disk and not managed."""
        if nexus_mod_id in self.managed_ids:
            return None
        match = self.matches.get(nexus_mod_id)
        if match is None or match.on_disk:
            return None
        return match


def winning_correlations(
    session: Session, game_id: int
) -> dict[int, tuple[ModNexusCorrelation, NexusDownload]]:
    """Best correlation per scanned group, deduplicated per Nexus mod id.

    Each group keeps its highest-scoring correlation. When several groups point at the same
    Nexus mod id, only the group with the highest score keeps it. Keyed by ``mod_group_id``.
    """
    rows = session.exec(
        select(ModNexusCorrelation, NexusDownload)
        .join(NexusDownload, ModNexusCorrelation.nexus_download_id == NexusDownload.id)
        .join(ModGroup, ModNexusCorrelation.mod_group_id == ModGroup.id)
        .where(ModGroup.game_id == game_id)
    ).all()

    best_per_group: dict[int, tuple[ModNexusCorrelation, NexusDownload]] = {}
    for corr, nd in rows:
        existing = best_per_group.get(corr.mod_group_id)
        if existing is None or corr.score > existing[0].score:
            best_per_group[corr.mod_group_id] = (corr, nd)

    best_per_nexus_id: dict[int, tuple[int, float]] = {}  # nexus_mod_id -> (group_id, score)
    for group_id, (corr, nd) in best_per_group.items():
        prev = best_per_nexus_id.get(nd.nexus_mod_id)
        if prev is None or corr.score > prev[1]:
            best_per_nexus_id[nd.nexus_mod_id] = (group_id, corr.score)

    winners = {group_id for group_id, _score in best_per_nexus_id.values()}
    return {gid: pair for gid, pair in best_per_group.items() if gid in winners}


def nexus_presence(game: Game, session: Session) -> Presence:
    """Which Nexus mod ids of *game* are managed, on disk, or possible matches."""
    managed_ids = {
        nid
        for nid in session.exec(
            select(InstalledMod.nexus_mod_id).where(InstalledMod.game_id == game.id)
        ).all()
        if nid is not None
    }

    matches: dict[int, DiskMatch] = {}
    for group_id, (corr, nd) in winning_correlations(session, game.id).items():  # type: ignore[arg-type]
        matches[nd.nexus_mod_id] = DiskMatch(
            mod_group_id=group_id,
            nexus_mod_id=nd.nexus_mod_id,
            score=corr.score,
            confirmed=corr.confirmed_by_user,
            on_disk=corr.confirmed_by_user or corr.score >= ON_DISK_MIN_SCORE,
        )
    return Presence(managed_ids=managed_ids, matches=matches)


def archive_nexus_ids(game: Game, session: Session, names: set[str]) -> dict[str, int]:
    """Nexus mod id per archive filename: from the name, else ArchiveNexusLink, else a job.

    Archives with no id from any of the three are left out.
    """
    if not names:
        return {}
    ids: dict[str, int] = {}
    for fn, mid in session.exec(
        select(ArchiveNexusLink.filename, ArchiveNexusLink.nexus_mod_id).where(
            ArchiveNexusLink.game_id == game.id,
            ArchiveNexusLink.filename.in_(names),  # type: ignore[attr-defined]
        )
    ).all():
        ids[fn] = mid
    for fn, mid in session.exec(
        select(DownloadJob.file_name, DownloadJob.nexus_mod_id).where(
            DownloadJob.game_id == game.id,
            DownloadJob.status == "completed",
            DownloadJob.file_name.in_(names),  # type: ignore[attr-defined]
        )
    ).all():
        ids.setdefault(fn, mid)
    for name in names:
        parsed_id = parse_mod_filename(name).nexus_mod_id
        if parsed_id is not None:
            ids[name] = parsed_id
    return ids


def archive_status(
    filename: str,
    nexus_mod_id: int | None,
    managed_archives: set[str],
    presence: Presence,
) -> ArchiveStatus:
    """The real state of one archive in the staging folder."""
    if filename in managed_archives:
        return "managed"
    if nexus_mod_id is None:
        return "orphan"
    if nexus_mod_id in presence.managed_ids:
        return "other_version"
    if presence.is_on_disk(nexus_mod_id):
        return "not_managed"
    if presence.possible(nexus_mod_id) is not None:
        return "possible_match"
    return "not_installed"
