import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from rippermod_manager.nexus.client import BASE_URL
from rippermod_manager.services import app_update_service


@pytest.fixture(autouse=True)
def _reset_app_update_state():
    """Module-level state is shared across tests — reset before each."""
    app_update_service._reset_to("idle")
    app_update_service._task = None
    app_update_service._cancel_event = None
    yield
    app_update_service._reset_to("idle")


def _set_api_key(client, key: str = "valid-key"):
    client.put(
        "/api/v1/settings/",
        json={"settings": {"nexus_api_key": key}},
    )


class TestGetStatus:
    def test_idle_by_default(self, client):
        r = client.get("/api/v1/app-update/download")
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "idle"
        assert body["downloaded_bytes"] == 0
        assert body["path"] is None


class TestStartDownload:
    def test_missing_api_key_returns_error(self, client):
        r = client.post("/api/v1/app-update/download")
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "error"
        assert body["error_code"] == "no_api_key"

    @respx.mock
    def test_premium_required_surfaces_code(self, client):
        _set_api_key(client)
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781.json").mock(
            return_value=httpx.Response(200, json={"version": "2.11.5"})
        )
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781/files.json").mock(
            return_value=httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "file_id": 9001,
                            "file_name": "RipperMod.Manager_2.11.5_x64-setup.exe",
                            "version": "2.11.5",
                            "size_in_bytes": 1024,
                            "uploaded_timestamp": 1700000000,
                        }
                    ]
                },
            )
        )
        respx.get(
            f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781/files/9001/download_link.json"
        ).mock(return_value=httpx.Response(403, json={"message": "premium required"}))

        r = client.post("/api/v1/app-update/download")
        body = r.json()
        assert body["state"] == "error"
        assert body["error_code"] == "premium_required"

    @respx.mock
    def test_no_exe_file_returns_error(self, client):
        _set_api_key(client)
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781.json").mock(
            return_value=httpx.Response(200, json={"version": "2.11.5"})
        )
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781/files.json").mock(
            return_value=httpx.Response(
                200, json={"files": [{"file_id": 1, "file_name": "notes.txt", "version": "1.0"}]}
            )
        )

        r = client.post("/api/v1/app-update/download")
        assert r.json()["error_code"] == "no_installer_found"

    @respx.mock
    def test_download_success_writes_file(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "rippermod_manager.routers.app_update.settings",
            type("S", (), {"data_dir": tmp_path})(),
        )
        _set_api_key(client)

        installer_bytes = b"FAKE_INSTALLER_BYTES"
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781.json").mock(
            return_value=httpx.Response(200, json={"version": "2.11.5"})
        )
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781/files.json").mock(
            return_value=httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "file_id": 9001,
                            "file_name": "RipperMod.Manager_2.11.5_x64-setup.exe",
                            "version": "2.11.5",
                            "size_in_bytes": len(installer_bytes),
                            "uploaded_timestamp": 1700000000,
                        }
                    ]
                },
            )
        )
        respx.get(
            f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781/files/9001/download_link.json"
        ).mock(
            return_value=httpx.Response(
                200,
                json=[{"URI": "https://cdn.example.test/installer.exe"}],
            )
        )
        respx.get("https://cdn.example.test/installer.exe").mock(
            return_value=httpx.Response(
                200,
                content=installer_bytes,
                headers={"Content-Length": str(len(installer_bytes))},
            )
        )

        r = client.post("/api/v1/app-update/download")
        body = r.json()
        assert body["state"] == "downloading"
        assert body["file_name"] == "RipperMod.Manager_2.11.5_x64-setup.exe"
        assert body["version"] == "2.11.5"

        # Drain the background task so state transitions to "ready" before assert.
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_wait_for_state("ready", timeout=5.0))
        finally:
            loop.close()

        status = client.get("/api/v1/app-update/download").json()
        assert status["state"] == "ready"
        dest = Path(status["path"])
        assert dest.exists()
        assert dest.read_bytes() == installer_bytes


async def _wait_for_state(target: str, timeout: float) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if app_update_service.get_status().state == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"State never reached {target!r} (current={app_update_service.get_status().state!r})"
    )


class TestCancel:
    def test_cancel_when_idle_returns_idle(self, client):
        r = client.post("/api/v1/app-update/download/cancel")
        assert r.status_code == 200
        assert r.json()["state"] == "idle"

    @respx.mock
    def test_cancel_during_download_resets_and_removes_part_file(
        self, client, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "rippermod_manager.routers.app_update.settings",
            type("S", (), {"data_dir": tmp_path})(),
        )
        _set_api_key(client)
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781.json").mock(
            return_value=httpx.Response(200, json={"version": "2.11.5"})
        )
        respx.get(f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781/files.json").mock(
            return_value=httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "file_id": 9001,
                            "file_name": "setup.exe",
                            "version": "2.11.5",
                            "size_in_bytes": 10 * 1024 * 1024,
                            "uploaded_timestamp": 1700000000,
                        }
                    ]
                },
            )
        )
        respx.get(
            f"{BASE_URL}/v1/games/cyberpunk2077/mods/27781/files/9001/download_link.json"
        ).mock(
            return_value=httpx.Response(200, json=[{"URI": "https://cdn.example.test/setup.exe"}])
        )

        async def _slow_body(_request):
            async def _gen():
                # Yield one chunk so the task gets past stream() setup, then block on the
                # cancel event so cancel() actually interrupts mid-flight.
                yield b"x" * 1024
                while not (
                    app_update_service._cancel_event is not None
                    and app_update_service._cancel_event.is_set()
                ):
                    await asyncio.sleep(0.05)
                yield b""

            return httpx.Response(
                200,
                content=_gen(),
                headers={"Content-Length": str(10 * 1024 * 1024)},
            )

        respx.get("https://cdn.example.test/setup.exe").mock(side_effect=_slow_body)

        r = client.post("/api/v1/app-update/download")
        assert r.json()["state"] == "downloading"
        dest_path = Path(r.json()["path"])
        part_path = dest_path.with_suffix(dest_path.suffix + ".part")

        r2 = client.post("/api/v1/app-update/download/cancel")
        assert r2.status_code == 200
        assert r2.json()["state"] in ("idle", "ready")
        assert not part_path.exists()


class TestPickLatestInstaller:
    def test_picks_version_match_over_newer_upload(self):
        files = [
            {"file_id": 1, "file_name": "old.exe", "version": "2.10.0", "uploaded_timestamp": 2000},
            {"file_id": 2, "file_name": "new.exe", "version": "2.11.5", "uploaded_timestamp": 1000},
        ]
        chosen = app_update_service._pick_latest_installer(files, "2.11.5")
        assert chosen is not None
        assert chosen["file_id"] == 2

    def test_falls_back_to_newest_upload_when_no_version_match(self):
        files = [
            {"file_id": 1, "file_name": "a.exe", "version": "2.10.0", "uploaded_timestamp": 2000},
            {"file_id": 2, "file_name": "b.exe", "version": "2.10.1", "uploaded_timestamp": 1000},
        ]
        chosen = app_update_service._pick_latest_installer(files, "9.9.9")
        assert chosen is not None
        assert chosen["file_id"] == 1

    def test_ignores_non_exe_files(self):
        files = [
            {"file_id": 1, "file_name": "readme.txt", "version": "2.11.5"},
            {
                "file_id": 2,
                "file_name": "installer.exe",
                "version": "2.11.5",
                "uploaded_timestamp": 1,
            },
        ]
        chosen = app_update_service._pick_latest_installer(files, "2.11.5")
        assert chosen is not None
        assert chosen["file_id"] == 2

    def test_returns_none_when_no_exe(self):
        files = [{"file_id": 1, "file_name": "readme.txt"}]
        assert app_update_service._pick_latest_installer(files, "2.11.5") is None
