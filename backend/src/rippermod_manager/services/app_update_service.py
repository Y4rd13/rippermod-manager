"""Self-update download orchestration for RipperMod Manager itself.

Premium-only in-app download of the latest installer to a known folder under
``data_dir/updates/``. The actual install is always user-initiated — the
backend never launches the installer. This keeps the flow on the safe side of
the Nexus auto-update prohibition (see docs/nexus-compliance.md).
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from rippermod_manager.nexus.client import (
    NexusClient,
    NexusPremiumRequiredError,
    NexusRateLimitError,
)

logger = logging.getLogger(__name__)

RIPPERMOD_NEXUS_DOMAIN = "cyberpunk2077"
RIPPERMOD_NEXUS_MOD_ID = 27781

UpdateState = Literal["idle", "downloading", "ready", "error"]


@dataclass
class AppUpdateStatus:
    state: UpdateState = "idle"
    version: str | None = None
    file_name: str | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


_status = AppUpdateStatus()
_lock = asyncio.Lock()
_cancel_event: asyncio.Event | None = None
_task: asyncio.Task[None] | None = None


def get_status() -> AppUpdateStatus:
    return _status


def _reset_to(state: UpdateState) -> None:
    _status.state = state
    _status.version = None
    _status.file_name = None
    _status.downloaded_bytes = 0
    _status.total_bytes = 0
    _status.path = None
    _status.error_code = None
    _status.error_message = None


def _fail(code: str, message: str) -> AppUpdateStatus:
    _status.state = "error"
    _status.error_code = code
    _status.error_message = message
    return _status


def _pick_latest_installer(
    files: list[dict[str, Any]], target_version: str | None
) -> dict[str, Any] | None:
    exe_files = [f for f in files if str(f.get("file_name", "")).lower().endswith(".exe")]
    if not exe_files:
        return None
    if target_version:
        matching = [f for f in exe_files if str(f.get("version", "")) == target_version]
        if matching:
            exe_files = matching
    exe_files.sort(key=lambda f: int(f.get("uploaded_timestamp", 0) or 0), reverse=True)
    return exe_files[0]


async def start_download(api_key: str | None, data_dir: Path) -> AppUpdateStatus:
    """Start (or join) a self-update download. Idempotent for the downloading state."""
    global _task, _cancel_event

    async with _lock:
        if _status.state == "downloading":
            return _status
        if not api_key:
            return _fail("no_api_key", "Nexus API key not configured")
        _reset_to("downloading")

    try:
        async with NexusClient(api_key) as client:
            info = await client.get_mod_info(RIPPERMOD_NEXUS_DOMAIN, RIPPERMOD_NEXUS_MOD_ID)
            target_version = str(info.get("version") or "") or None
            files_resp = await client.get_mod_files(RIPPERMOD_NEXUS_DOMAIN, RIPPERMOD_NEXUS_MOD_ID)
            installer = _pick_latest_installer(files_resp.get("files", []), target_version)
            if not installer:
                return _fail("no_installer_found", "No installer .exe found on the Nexus mod page")
            links = await client.get_download_links(
                RIPPERMOD_NEXUS_DOMAIN,
                RIPPERMOD_NEXUS_MOD_ID,
                int(installer["file_id"]),
            )
    except NexusPremiumRequiredError:
        return _fail("premium_required", "A Premium Nexus account is required for in-app download")
    except NexusRateLimitError as exc:
        logger.warning("App update metadata fetch hit Nexus rate limit: %s", exc)
        return _fail("rate_limited", "Nexus API rate limit reached, try again later")
    except httpx.HTTPError as exc:
        logger.warning("App update metadata fetch failed: %s", exc)
        return _fail("network_error", f"Could not reach Nexus: {exc}")

    if not links or not links[0].get("URI"):
        return _fail("no_download_link", "Nexus returned no download URL")

    cdn_url = links[0]["URI"]
    file_name = Path(str(installer["file_name"])).name
    dest_dir = data_dir / "updates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file_name

    _status.file_name = file_name
    _status.version = str(installer.get("version") or "") or target_version
    _status.total_bytes = int(installer.get("size_in_bytes") or 0)
    _status.path = str(dest_path)

    _cancel_event = asyncio.Event()
    _task = asyncio.create_task(_run_download(cdn_url, dest_path, _cancel_event))
    return _status


async def _run_download(cdn_url: str, dest_path: Path, cancel_event: asyncio.Event) -> None:
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    try:
        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client,
            client.stream("GET", cdn_url) as resp,
        ):
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            if total and not _status.total_bytes:
                _status.total_bytes = total
            with open(part_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65_536):
                    if cancel_event.is_set():
                        raise asyncio.CancelledError("Download cancelled")
                    f.write(chunk)
                    _status.downloaded_bytes += len(chunk)
        part_path.replace(dest_path)
        _status.state = "ready"
        _status.path = str(dest_path)
        logger.info("Self-update installer ready at %s", dest_path)
    except asyncio.CancelledError:
        part_path.unlink(missing_ok=True)
        _reset_to("idle")
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Self-update download failed: %s", exc)
        part_path.unlink(missing_ok=True)
        _fail("download_failed", str(exc))


async def cancel() -> AppUpdateStatus:
    if _cancel_event and not _cancel_event.is_set():
        _cancel_event.set()
    if _task and not _task.done():
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(_task, timeout=5.0)
    return _status


async def shutdown() -> None:
    """Cancel any in-flight self-update download on app shutdown."""
    if _status.state == "downloading":
        await cancel()
