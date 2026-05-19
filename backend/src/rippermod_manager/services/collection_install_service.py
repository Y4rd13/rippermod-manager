"""Orchestrator for one-click Nexus Collections install (#222).

PR C scope -- premium-only single-phase install (the happy path Vortex calls
"premium auto-download"). Sequencing mirrors the rough shape of Vortex's
``InstallDriver``:

  1. Resolve the Collection revision -> manifest (via GraphQL,
     :func:`nexus.graphql_client.NexusGraphQLClient.get_collection_revision`)
  2. Persist an :class:`InstalledCollection` row in ``pending`` status
  3. For each mod in the requested set:
       - download via :func:`services.download_service.create_and_start_download`
         (tagged with ``installed_collection_id`` for batch tracking)
       - wait for the download to finish (poll the DB)
       - install via :func:`services.install_service.install_mod` with
         ``auto_deploy=False`` so we don't redeploy N times
  4. Run :func:`services.vfs.deploy_service.deploy` once at the end
  5. Update collection status (``installed`` / ``partial`` / ``failed``)

Free-tier flow (per-file ``nxm://`` user clicks) is intentionally out of
scope for PR C -- that lands in PR G. Callers check ``is_premium`` before
invoking ``start_install`` and return a 400 when False.

FOMOD archives are routed through :func:`_install_fomod_archive`, which
parses the ``fomod/ModuleConfig.xml`` from the archive, resolves any
pre-recorded ``fomod_choices`` from the manifest into FOMOD step/group/
plugin indices via :func:`services.fomod_choice_resolver.resolve_choices`,
then calls :func:`install_fomod` with ``auto_deploy=False``. A FOMOD
without recorded choices installs only its required-files baseline (the
"click through with nothing ticked" equivalent).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlmodel import Session, select

from rippermod_manager.models.collection import InstalledCollection
from rippermod_manager.models.download import DownloadJob
from rippermod_manager.models.game import Game
from rippermod_manager.nexus.client import NexusRateLimitError
from rippermod_manager.nexus.graphql_client import (
    NexusGraphQLClient,
    NexusGraphQLError,
)
from rippermod_manager.schemas.collection import (
    CollectionInstallRequest,
    CollectionModEntry,
    CollectionPreviewOut,
    CollectionProgressEvent,
)
from rippermod_manager.services.paths import resolve_mods_dir

logger = logging.getLogger(__name__)

# Polling interval while waiting for a download job to finish. Short enough
# that the UI feels responsive, long enough not to thrash SQLite.
_DOWNLOAD_POLL_INTERVAL_S = 1.0
# Hard cap to avoid waiting forever if the download silently hangs.
_DOWNLOAD_TIMEOUT_S = 60 * 30  # 30 min -- large mods on slow links

# In-memory event queues keyed by InstalledCollection.id. The SSE endpoint
# subscribes to one of these to stream progress events. Cleaned up when the
# orchestrator emits its final ``done`` / ``error`` event.
_event_queues: dict[int, asyncio.Queue[CollectionProgressEvent | None]] = {}
# Background-task tracking so we don't lose references (asyncio.create_task
# only holds a weak ref). Mirrors the pattern in download_service.
_background_tasks: set[asyncio.Task[Any]] = set()


class CollectionInstallInProgressError(Exception):
    """Raised by :func:`start_install` when the same (game, slug) is still
    being installed. Prevents the race where a second start_install would
    overwrite the queue + status of the first, then the first task's
    ``finally _close_queue`` would kill the second subscriber's stream."""

    def __init__(self, collection_id: int) -> None:
        self.collection_id = collection_id
        super().__init__(f"Collection install {collection_id} is already in progress")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_preview(
    slug: str, revision: int, game_domain: str, api_key: str
) -> CollectionPreviewOut:
    """Fetch and shape a Collection revision into the preview-dialog payload.

    Raises :class:`httpx.HTTPError`, :class:`NexusRateLimitError`, or
    :class:`NexusGraphQLError` -- the caller (router) translates these.
    """
    async with NexusGraphQLClient(api_key) as gql:
        rev = await gql.get_collection_revision(slug, revision, game_domain)

    if not rev:
        raise ValueError(f"Collection '{slug}' revision {revision} not found on Nexus")

    return _shape_preview(slug, rev)


def start_install(
    game: Game,
    request: CollectionInstallRequest,
    session: Session,
    api_key: str,
    preview: CollectionPreviewOut,
) -> InstalledCollection:
    """Persist an InstalledCollection row and spawn the background runner.

    Returns immediately. Caller subscribes to ``stream_events(collection.id)``
    to follow progress.
    """
    assert game.id is not None, "game must be persisted"

    # Apply skip-list + optional filter to the manifest's mod set.
    skip = set(request.skip_mod_ids)
    mods_to_install = [
        m
        for m in preview.mods
        if m.nexus_mod_id not in skip and (request.include_optional or not m.optional)
    ]

    collection = _upsert_collection_row(game, preview, session)

    # Refuse to start a second install while the first is still running for
    # this (game, slug). Without this guard, ``_event_queues[id]`` would be
    # overwritten and the old task's ``finally _close_queue`` would kill the
    # new subscriber's stream mid-flight.
    if collection.id is not None and collection.id in _event_queues:
        raise CollectionInstallInProgressError(collection.id)

    collection.status = "pending"
    collection.total_mods = len(mods_to_install)
    collection.completed_mods = 0
    collection.failed_mods = 0
    collection.skipped_mods = 0
    collection.error = ""
    collection.started_at = datetime.now(UTC)
    collection.finished_at = None
    session.add(collection)
    session.commit()
    session.refresh(collection)

    assert collection.id is not None
    _event_queues[collection.id] = asyncio.Queue()

    task = asyncio.create_task(
        _run_install(
            collection_id=collection.id,
            game_id=game.id,
            install_path=game.install_path,
            mods_dir=game.mods_dir,
            api_key=api_key,
            mods=mods_to_install,
        ),
        name=f"collection-install-{collection.id}",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return collection


async def stream_events(collection_id: int) -> AsyncIterator[CollectionProgressEvent]:
    """SSE-friendly async iterator over an install's progress events.

    Yields events until the install completes (sentinel ``None`` on the
    queue). If no install is active for ``collection_id``, yields nothing.
    """
    q = _event_queues.get(collection_id)
    if q is None:
        return
    while True:
        event = await q.get()
        if event is None:
            break
        yield event


def uninstall_collection(collection_id: int, session: Session) -> dict[str, int]:
    """Drop an InstalledCollection and uninstall every mod that belonged to it.

    Returns a small summary dict: ``{"removed_mods": N, "failed_mods": M}``.
    The single end-of-batch deploy mirrors the install path so the game-dir
    state lands consistent.

    Refuses to run while the install is still in flight (the queue is still
    registered) — the caller should cancel or wait first.
    """
    from rippermod_manager.models.install import InstalledMod
    from rippermod_manager.services.install_service import uninstall_mod
    from rippermod_manager.services.vfs.deploy_service import deploy

    if collection_id in _event_queues:
        # PR C's CollectionInstallInProgressError lands in this module via
        # the same chain; until those PRs are merged + this chain rebased,
        # raise the simpler RuntimeError that the router maps to HTTP 409.
        raise RuntimeError(f"Collection install {collection_id} is still in progress")

    collection = session.get(InstalledCollection, collection_id)
    if collection is None:
        raise ValueError(f"Collection {collection_id} not found")

    game = session.get(Game, collection.game_id)
    if game is None:
        raise ValueError(f"Game {collection.game_id} not found")

    children = session.exec(
        select(InstalledMod).where(InstalledMod.installed_collection_id == collection_id)
    ).all()

    removed = 0
    failed = 0
    for child in children:
        try:
            uninstall_mod(child, game, session)
            removed += 1
        except (OSError, RuntimeError):
            logger.exception(
                "Uninstall of mod %s (id=%d) from collection %d failed",
                child.name,
                child.id,
                collection_id,
            )
            failed += 1

    # Drop the parent row last so child rows have their FK pointing at a
    # live row while uninstall_mod runs.
    session.delete(collection)
    session.commit()

    try:
        deploy(game, session)
    except (OSError, RuntimeError):
        logger.exception("Post-uninstall deploy failed for collection %d", collection_id)

    return {"removed_mods": removed, "failed_mods": failed}


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _shape_preview(slug: str, rev: dict[str, Any]) -> CollectionPreviewOut:
    """Translate the raw GraphQL revision payload into the API schema."""
    coll = rev.get("collection") or {}
    user = coll.get("user") or {}
    tile = coll.get("tileImage") or {}

    mods: list[CollectionModEntry] = []
    total_size = 0
    for mf in rev.get("modFiles") or []:
        file = mf.get("file") or {}
        mod = file.get("mod") or {}
        file_id = file.get("fileId")
        mod_id = mod.get("modId")
        if not file_id or not mod_id:
            # Malformed entry -- skip rather than fail the whole preview.
            continue
        size = int(file.get("size") or 0)
        total_size += size
        mods.append(
            CollectionModEntry(
                nexus_mod_id=int(mod_id),
                nexus_file_id=int(file_id),
                name=mod.get("name") or file.get("name") or "",
                version=file.get("version") or mod.get("version") or "",
                author=mod.get("author") or "",
                summary=mod.get("summary") or "",
                size_bytes=size,
                picture_url=mod.get("pictureUrl") or "",
                optional=bool(mf.get("optional")),
                phase=0,
            )
        )

    return CollectionPreviewOut(
        slug=slug,
        revision_id=str(rev.get("id") or ""),
        revision_number=int(rev.get("revisionNumber") or 0),
        name=coll.get("name") or "",
        summary=coll.get("summary") or "",
        description=coll.get("description") or "",
        author=user.get("name") or "",
        tile_image_url=tile.get("url") or "",
        endorsements=int(coll.get("endorsements") or 0),
        total_downloads=int(coll.get("totalDownloads") or 0),
        total_size_bytes=total_size,
        mods=mods,
    )


def _upsert_collection_row(
    game: Game, preview: CollectionPreviewOut, session: Session
) -> InstalledCollection:
    """Find-or-create the InstalledCollection row for this (game, slug)."""
    existing = session.exec(
        select(InstalledCollection).where(
            InstalledCollection.game_id == game.id,
            InstalledCollection.slug == preview.slug,
        )
    ).first()

    if existing is None:
        existing = InstalledCollection(
            game_id=game.id,  # type: ignore[arg-type]
            slug=preview.slug,
        )
        session.add(existing)

    existing.revision_id = preview.revision_id
    existing.revision_number = preview.revision_number
    existing.collection_name = preview.name
    existing.author_name = preview.author
    existing.summary = preview.summary
    existing.tile_image_url = preview.tile_image_url
    return existing


async def _emit(
    collection_id: int,
    *,
    phase: str,
    message: str,
    percent: int,
    completed: int,
    failed: int,
    skipped: int,
    total: int,
    current_mod: str = "",
    status: str = "",
) -> None:
    """Push an event onto the per-install queue (if any subscriber)."""
    q = _event_queues.get(collection_id)
    if q is None:
        return
    await q.put(
        CollectionProgressEvent(
            phase=phase,
            message=message,
            percent=percent,
            completed=completed,
            failed=failed,
            skipped=skipped,
            total=total,
            current_mod=current_mod,
            status=status,
        )
    )


def _close_queue(collection_id: int) -> None:
    q = _event_queues.pop(collection_id, None)
    if q is not None:
        # Drop the sentinel so any subscriber's loop exits cleanly.
        try:
            q.put_nowait(None)
        except asyncio.QueueFull:
            logger.debug("Event queue full for collection %d", collection_id)


def _install_archive(
    *,
    game: Game,
    archive_path: Path,
    entry: CollectionModEntry,
    collection_id: int,
    session: Session,
) -> str:
    """Install one downloaded archive on behalf of a collection.

    Returns one of ``"completed"`` / ``"skipped"`` / ``"failed"``. The
    InstalledMod row (if created) is tagged with the collection FK + phase
    + optional flag before this function returns.

    Routes between :func:`install_mod` (regular archives) and
    :func:`install_fomod` (when the archive is a FOMOD installer with
    pre-recorded ``fomod_choices`` in the manifest, or when there are no
    choices and we install the required-only baseline).
    """
    from rippermod_manager.matching.filename_parser import parse_mod_filename
    from rippermod_manager.services.install_service import install_mod

    parsed = parse_mod_filename(archive_path.name)

    try:
        install_mod(
            game=game,
            archive_path=archive_path,
            session=session,
            auto_deploy=False,
        )
        _tag_installed(session, game.id, parsed.name, collection_id, entry)  # type: ignore[arg-type]
        return "completed"
    except ValueError as exc:
        msg = str(exc)
        if "already installed" in msg:
            logger.info("Collection %d: %s already installed, skipping", collection_id, parsed.name)
            return "skipped"
        if "FOMOD" not in msg:
            logger.exception("Collection %d: install_mod failed for %s", collection_id, parsed.name)
            return "failed"
    except (OSError, RuntimeError):
        logger.exception(
            "Collection %d: unexpected install failure for %s", collection_id, parsed.name
        )
        return "failed"

    # FOMOD branch: parse the config, resolve recorded choices, run the
    # non-interactive installer.
    return _install_fomod_archive(
        game=game,
        archive_path=archive_path,
        entry=entry,
        mod_name=parsed.name,
        collection_id=collection_id,
        session=session,
    )


def _install_fomod_archive(
    *,
    game: Game,
    archive_path: Path,
    entry: CollectionModEntry,
    mod_name: str,
    collection_id: int,
    session: Session,
) -> str:
    """Drive the FOMOD installer non-interactively from manifest choices."""
    from rippermod_manager.archive.handler import open_archive
    from rippermod_manager.services.fomod_choice_resolver import resolve_choices
    from rippermod_manager.services.fomod_config_parser import parse_fomod_config
    from rippermod_manager.services.fomod_install_service import (
        compute_file_list,
        install_fomod,
    )

    try:
        with open_archive(archive_path) as archive:
            entries = archive.list_entries()
            config_entry = next(
                (
                    e
                    for e in entries
                    if not e.is_dir
                    and e.filename.replace("\\", "/").lower().endswith("fomod/moduleconfig.xml")
                ),
                None,
            )
            if config_entry is None:
                logger.warning(
                    "Collection %d: %s claims FOMOD but no ModuleConfig.xml found",
                    collection_id,
                    mod_name,
                )
                return "failed"

            normalised = config_entry.filename.replace("\\", "/")
            fomod_idx = normalised.lower().rfind("fomod/moduleconfig.xml")
            fomod_prefix = normalised[:fomod_idx].rstrip("/") if fomod_idx > 0 else ""
            xml_bytes = archive.read_file(config_entry)

        config = parse_fomod_config(xml_bytes)
        selections = resolve_choices(config, entry.fomod_choices)
        resolved = compute_file_list(config, selections, entries, fomod_prefix)

        install_fomod(
            game=game,
            archive_path=archive_path,
            session=session,
            resolved_files=resolved,
            mod_name=mod_name,
            nexus_mod_id=entry.nexus_mod_id,
            auto_deploy=False,
        )
    except ValueError as exc:
        if "already installed" in str(exc):
            logger.info(
                "Collection %d: FOMOD %s already installed, skipping", collection_id, mod_name
            )
            return "skipped"
        logger.exception("Collection %d: FOMOD install rejected for %s", collection_id, mod_name)
        return "failed"
    except (OSError, RuntimeError):
        logger.exception("Collection %d: FOMOD install crashed for %s", collection_id, mod_name)
        return "failed"

    _tag_installed(session, game.id, mod_name, collection_id, entry)  # type: ignore[arg-type]
    return "completed"


def _tag_installed(
    session: Session,
    game_id: int,
    mod_name: str,
    collection_id: int,
    entry: CollectionModEntry,
) -> None:
    """Mark a freshly installed mod as part of this collection."""
    from rippermod_manager.models.install import InstalledMod

    installed = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game_id,
            InstalledMod.name == mod_name,
        )
    ).first()
    if installed is not None:
        installed.installed_collection_id = collection_id
        installed.collection_phase = entry.phase
        installed.is_optional = entry.optional
        session.add(installed)
        session.commit()


async def _wait_for_download(job_id: int) -> DownloadJob:
    """Poll the DB until the download job leaves the in-flight states."""
    from rippermod_manager.database import engine

    elapsed = 0.0
    while elapsed < _DOWNLOAD_TIMEOUT_S:
        await asyncio.sleep(_DOWNLOAD_POLL_INTERVAL_S)
        elapsed += _DOWNLOAD_POLL_INTERVAL_S
        with Session(engine) as s:
            job = s.get(DownloadJob, job_id)
            if job is None:
                raise RuntimeError(f"Download job {job_id} vanished")
            if job.status in ("completed", "failed", "cancelled"):
                return job
    raise TimeoutError(f"Download job {job_id} did not complete in {_DOWNLOAD_TIMEOUT_S}s")


async def _run_install(
    *,
    collection_id: int,
    game_id: int,
    install_path: str,
    mods_dir: str | None,
    api_key: str,
    mods: list[CollectionModEntry],
) -> None:
    """Background task: download + install each mod, deploy once at the end."""
    from rippermod_manager.database import engine
    from rippermod_manager.services.download_service import create_and_start_download
    from rippermod_manager.services.vfs.deploy_service import deploy

    completed = 0
    failed = 0
    skipped = 0
    total = len(mods)

    def _update(status: str, **fields: Any) -> None:
        with Session(engine) as s:
            row = s.get(InstalledCollection, collection_id)
            if row is None:
                return
            row.status = status
            row.completed_mods = completed
            row.failed_mods = failed
            row.skipped_mods = skipped
            for k, v in fields.items():
                setattr(row, k, v)
            s.add(row)
            s.commit()

    def _pct() -> int:
        if total == 0:
            return 100
        return int(((completed + failed + skipped) / total) * 100)

    try:
        if total == 0:
            _update("installed", finished_at=datetime.now(UTC))
            await _emit(
                collection_id,
                phase="done",
                message="No mods to install",
                percent=100,
                completed=0,
                failed=0,
                skipped=0,
                total=0,
                status="installed",
            )
            return

        _update("downloading")

        for entry in mods:
            current = entry.name or f"mod #{entry.nexus_mod_id}"
            await _emit(
                collection_id,
                phase="download",
                message=f"Downloading {current}",
                percent=_pct(),
                completed=completed,
                failed=failed,
                skipped=skipped,
                total=total,
                current_mod=current,
                status="downloading",
            )

            with Session(engine) as s:
                game = s.get(Game, game_id)
                if game is None:
                    raise RuntimeError(f"Game {game_id} vanished mid-install")
                try:
                    job = await create_and_start_download(
                        game=game,
                        nexus_mod_id=entry.nexus_mod_id,
                        nexus_file_id=entry.nexus_file_id,
                        api_key=api_key,
                        session=s,
                    )
                    # Tag the job so the orchestrator can aggregate later.
                    job.installed_collection_id = collection_id
                    s.add(job)
                    s.commit()
                    s.refresh(job)
                    job_id = job.id
                    job_status = job.status
                except (NexusRateLimitError, NexusGraphQLError, httpx.HTTPError) as exc:
                    failed += 1
                    logger.warning(
                        "Collection %d: download kick-off failed for mod %d: %s",
                        collection_id,
                        entry.nexus_mod_id,
                        exc,
                    )
                    await _emit(
                        collection_id,
                        phase="download",
                        message=f"Failed to start download for {current}: {exc}",
                        percent=_pct(),
                        completed=completed,
                        failed=failed,
                        skipped=skipped,
                        total=total,
                        current_mod=current,
                        status="downloading",
                    )
                    _update("downloading")
                    continue

            if job_status == "failed":
                failed += 1
                _update("downloading")
                continue

            assert job_id is not None
            try:
                job_done = await _wait_for_download(job_id)
            except (RuntimeError, TimeoutError) as exc:
                failed += 1
                logger.warning(
                    "Collection %d: download wait failed for job %d: %s",
                    collection_id,
                    job_id,
                    exc,
                )
                _update("downloading")
                continue

            if job_done.status != "completed":
                failed += 1
                _update("downloading")
                continue

            # Install the freshly downloaded archive.
            await _emit(
                collection_id,
                phase="install",
                message=f"Installing {current}",
                percent=_pct(),
                completed=completed,
                failed=failed,
                skipped=skipped,
                total=total,
                current_mod=current,
                status="installing",
            )
            _update("installing")

            archive_path = resolve_mods_dir(install_path, mods_dir) / job_done.file_name
            with Session(engine) as s:
                game = s.get(Game, game_id)
                if game is None:
                    raise RuntimeError(f"Game {game_id} vanished mid-install")
                result = _install_archive(
                    game=game,
                    archive_path=archive_path,
                    entry=entry,
                    collection_id=collection_id,
                    session=s,
                )

            if result == "completed":
                completed += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1

            _update("installing")

        # One deploy at the end of the run -- much cheaper than N per-mod.
        await _emit(
            collection_id,
            phase="deploy",
            message="Deploying all installed mods",
            percent=_pct(),
            completed=completed,
            failed=failed,
            skipped=skipped,
            total=total,
            status="installing",
        )
        try:
            with Session(engine) as s:
                game = s.get(Game, game_id)
                if game is not None:
                    deploy(game, s)
        except (OSError, RuntimeError):
            logger.exception("Collection %d: final deploy failed", collection_id)

        # Final state -- success / partial.
        if failed == 0 and skipped == 0:
            final_status = "installed"
        elif completed == 0:
            final_status = "failed"
        else:
            final_status = "partial"

        _update(final_status, finished_at=datetime.now(UTC))
        await _emit(
            collection_id,
            phase="done",
            message=f"Installed {completed} / {total} mods",
            percent=100,
            completed=completed,
            failed=failed,
            skipped=skipped,
            total=total,
            status=final_status,
        )

    except Exception as exc:
        logger.exception("Collection %d install crashed", collection_id)
        _update("failed", finished_at=datetime.now(UTC), error=str(exc))
        await _emit(
            collection_id,
            phase="error",
            message=f"Install crashed: {exc}",
            percent=_pct(),
            completed=completed,
            failed=failed,
            skipped=skipped,
            total=total,
            status="failed",
        )
    finally:
        _close_queue(collection_id)


def collection_path(archive_filename: str, install_path: str, mods_dir: str | None) -> Path:
    """Resolve the absolute path of a downloaded mod archive (test hook)."""
    return resolve_mods_dir(install_path, mods_dir) / archive_filename
