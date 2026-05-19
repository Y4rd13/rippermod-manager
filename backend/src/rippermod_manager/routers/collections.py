"""HTTP surface for Nexus Collections install (#222).

Endpoints (mounted under ``/api/v1``):

  GET  /games/{game_name}/collections/{slug}/revision/{rev}/preview
       Returns the manifest + collection identity used by the preview dialog.

  POST /games/{game_name}/collections/install
       Persists an ``InstalledCollection`` row and kicks off the background
       install runner. Returns the row immediately so the UI can navigate to
       the progress screen.

  GET  /games/{game_name}/collections
       Lists every ``InstalledCollection`` for a game (Installed-tab grouping).

  GET  /collections/{collection_id}/status
       Polled snapshot of the row (status + counters).

  GET  /collections/{collection_id}/stream
       Server-Sent Events stream of ``CollectionProgressEvent``s. Closes when
       the install reaches a terminal state.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from rippermod_manager.database import get_session
from rippermod_manager.models.collection import InstalledCollection
from rippermod_manager.nexus.client import (
    NexusClient,
    NexusRateLimitError,
)
from rippermod_manager.nexus.graphql_client import NexusGraphQLError
from rippermod_manager.routers.deps import get_game_or_404
from rippermod_manager.schemas.collection import (
    CollectionActionResult,
    CollectionInstallRequest,
    CollectionPreviewOut,
    CollectionSkipNxmRequest,
    CollectionStatusOut,
    UninstallCollectionOut,
)
from rippermod_manager.services import collection_install_service
from rippermod_manager.services.collection_install_service import (
    CollectionInstallInProgressError,
)
from rippermod_manager.services.settings_helpers import get_setting

logger = logging.getLogger(__name__)

router = APIRouter(tags=["collections"])


def _require_api_key(session: Session) -> str:
    key = get_setting(session, "nexus_api_key")
    if not key:
        raise HTTPException(400, "Nexus API key not configured")
    return key


def _row_to_status(row: InstalledCollection) -> CollectionStatusOut:
    return CollectionStatusOut(
        id=row.id,  # type: ignore[arg-type]
        game_id=row.game_id,
        slug=row.slug,
        revision_number=row.revision_number,
        name=row.collection_name,
        author=row.author_name,
        summary=row.summary,
        tile_image_url=row.tile_image_url,
        status=row.status,
        total_mods=row.total_mods,
        completed_mods=row.completed_mods,
        failed_mods=row.failed_mods,
        skipped_mods=row.skipped_mods,
        started_at=row.started_at,
        finished_at=row.finished_at,
        error=row.error,
    )


@router.get(
    "/games/{game_name}/collections/{slug}/revision/{rev}/preview",
    response_model=CollectionPreviewOut,
)
async def preview_collection(
    game_name: str,
    slug: str,
    rev: int,
    session: Session = Depends(get_session),
) -> CollectionPreviewOut:
    """Resolve a Collection revision and return the install-preview payload."""
    game = get_game_or_404(game_name, session)
    api_key = _require_api_key(session)
    try:
        return await collection_install_service.fetch_preview(
            slug=slug,
            revision=rev,
            game_domain=game.domain_name,
            api_key=api_key,
        )
    except NexusRateLimitError as exc:
        raise HTTPException(429, "Nexus rate limit reached, try again later") from exc
    except NexusGraphQLError as exc:
        raise HTTPException(502, f"Nexus GraphQL error: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Failed to reach Nexus: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post(
    "/games/{game_name}/collections/install",
    response_model=CollectionStatusOut,
    status_code=202,
)
async def install_collection(
    game_name: str,
    body: CollectionInstallRequest,
    session: Session = Depends(get_session),
) -> CollectionStatusOut:
    """Kick off a background install. Returns the row immediately (202 Accepted)."""
    game = get_game_or_404(game_name, session)
    api_key = _require_api_key(session)

    # Free-tier accounts go through the per-file ``awaiting_nxm`` flow inside
    # the orchestrator (PR G, #222) -- no premium-only refusal here anymore.
    # We still need ``is_premium`` to pick the right branch downstream.
    async with NexusClient(api_key) as client:
        key_result = await client.validate_key()
    if not key_result.valid:
        raise HTTPException(401, "Nexus API key rejected; reconfigure it in Settings.")

    try:
        preview = await collection_install_service.fetch_preview(
            slug=body.slug,
            revision=body.revision,
            game_domain=game.domain_name,
            api_key=api_key,
        )
    except NexusRateLimitError as exc:
        raise HTTPException(429, "Nexus rate limit reached, try again later") from exc
    except NexusGraphQLError as exc:
        raise HTTPException(502, f"Nexus GraphQL error: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Failed to reach Nexus: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    try:
        row = collection_install_service.start_install(
            game=game,
            request=body,
            session=session,
            api_key=api_key,
            preview=preview,
            is_premium=key_result.is_premium,
        )
    except CollectionInstallInProgressError as exc:
        raise HTTPException(
            409,
            f"Collection install {exc.collection_id} is already in progress; "
            f"wait for it to finish (or hit the cancel endpoint) before re-installing.",
        ) from exc
    return _row_to_status(row)


@router.get("/games/{game_name}/collections", response_model=list[CollectionStatusOut])
def list_collections(
    game_name: str,
    session: Session = Depends(get_session),
) -> list[CollectionStatusOut]:
    """List every InstalledCollection for the game (Installed-tab grouping)."""
    game = get_game_or_404(game_name, session)
    rows = session.exec(
        select(InstalledCollection)
        .where(InstalledCollection.game_id == game.id)
        .order_by(InstalledCollection.started_at.desc())  # type: ignore[union-attr]
    ).all()
    return [_row_to_status(r) for r in rows]


@router.get("/collections/{collection_id}/status", response_model=CollectionStatusOut)
def get_collection_status(
    collection_id: int,
    session: Session = Depends(get_session),
) -> CollectionStatusOut:
    row = session.get(InstalledCollection, collection_id)
    if row is None:
        raise HTTPException(404, "Collection not found")
    return _row_to_status(row)


@router.post(
    "/collections/{collection_id}/skip-pending-nxm",
    response_model=CollectionActionResult,
)
def skip_pending_nxm(
    collection_id: int,
    body: CollectionSkipNxmRequest,
    session: Session = Depends(get_session),
) -> CollectionActionResult:
    """Skip the mod a free-tier orchestrator is currently waiting for.

    The orchestrator wakes from its NXM wait, marks the mod as ``skipped``
    (not ``failed``), and advances to the next entry. No-op when no
    matching waiter is registered (``ok=False``, no error) -- this can
    happen if the user clicks Skip right after the download starts on its
    own, or after a backend restart.
    """
    row = session.get(InstalledCollection, collection_id)
    if row is None:
        raise HTTPException(404, "Collection not found")

    fired = collection_install_service.request_skip_nxm(body.nexus_mod_id, body.nexus_file_id)
    return CollectionActionResult(
        ok=fired,
        message=(
            "Skip signal delivered to the orchestrator."
            if fired
            else "No active NXM wait for this mod; install may have already advanced."
        ),
    )


@router.post(
    "/collections/{collection_id}/cancel",
    response_model=CollectionActionResult,
)
def cancel_collection_install(
    collection_id: int,
    session: Session = Depends(get_session),
) -> CollectionActionResult:
    """Cancel an in-flight orchestrator. Marks the row as ``cancelled``.

    Returns ``ok=True`` when an active orchestrator was found and signalled
    to stop. ``ok=False`` when there is nothing to cancel (already
    finished, never started, or backend restarted in between). To remove
    the row + its mods, follow up with ``DELETE /collections/{id}``.
    """
    row = session.get(InstalledCollection, collection_id)
    if row is None:
        raise HTTPException(404, "Collection not found")

    fired = collection_install_service.cancel_install(collection_id)
    return CollectionActionResult(
        ok=fired,
        message=(
            "Cancellation signal delivered; orchestrator winding down."
            if fired
            else "No active install task; the row is already in a terminal state."
        ),
    )


@router.delete("/collections/{collection_id}", response_model=UninstallCollectionOut)
def uninstall_collection(
    collection_id: int,
    session: Session = Depends(get_session),
) -> UninstallCollectionOut:
    """Drop an InstalledCollection and uninstall every mod that was part of it.

    Returns the cascade counts. Refuses (409) while the collection is still
    being installed — cancel or wait first.
    """
    try:
        result = collection_install_service.uninstall_collection(collection_id, session)
    except RuntimeError as exc:
        # "Install still in progress" — see comment in uninstall_collection.
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return UninstallCollectionOut(**result)


@router.get("/collections/{collection_id}/stream")
async def stream_collection_progress(
    collection_id: int,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """SSE stream of progress events. Closes when the install settles.

    If the install already finished before the client connected, the row's
    final state is emitted as a single ``done`` event and the stream closes.
    """
    row = session.get(InstalledCollection, collection_id)
    if row is None:
        raise HTTPException(404, "Collection not found")

    async def gen():
        # Emit an initial state snapshot so the UI can render immediately
        # without having to make a separate /status round-trip.
        snapshot = _row_to_status(row)
        yield f"data: {snapshot.model_dump_json()}\n\n"

        async for event in collection_install_service.stream_events(collection_id):
            yield f"data: {event.model_dump_json()}\n\n"

        # If no live install was attached (e.g. backend restarted while the
        # row was in-progress, or install already finished), send a synthetic
        # closing event so the EventSource on the UI side resolves.
        with Session(_engine_for_close()) as s:
            final = s.get(InstalledCollection, collection_id)
            if final is not None and final.status in (
                "installed",
                "partial",
                "failed",
                "cancelled",
            ):
                yield (
                    "event: close\n"
                    "data: " + json.dumps({"status": final.status, "id": collection_id}) + "\n\n"
                )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _engine_for_close():
    # Wrapped in a function so tests can monkey-patch the engine cleanly.
    from rippermod_manager.database import engine

    return engine
