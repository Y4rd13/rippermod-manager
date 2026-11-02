"""Tests for the downloads router."""

import httpx
import respx

from rippermod_manager.nexus.client import BASE_URL

G = "/api/v1/games/Cyberpunk 2077/downloads"


def _setup(client):
    client.post(
        "/api/v1/games/",
        json={
            "name": "Cyberpunk 2077",
            "domain_name": "cyberpunk2077",
            "install_path": client.cp_install,
        },
    )
    client.put("/api/v1/settings/", json={"settings": {"nexus_api_key": "test-api-key"}})


def _mock_validate(is_premium: bool) -> None:
    respx.get(f"{BASE_URL}/v1/users/validate.json").mock(
        return_value=httpx.Response(200, json={"name": "u", "is_premium": is_premium})
    )


def _mock_one_main_file(file_id: int = 9001) -> None:
    respx.get(url__regex=r".*/mods/107/files\.json.*").mock(
        return_value=httpx.Response(
            200,
            json={"files": [{"file_id": file_id, "category_id": 1, "file_name": "a.zip"}]},
        )
    )


@respx.mock
def test_free_download_returns_files_url_with_file_id(client):
    _setup(client)
    _mock_validate(False)
    r = client.post(f"{G}/", json={"nexus_mod_id": 107, "nexus_file_id": 9001})
    assert r.json()["requires_nxm"] is True
    assert (
        r.json()["nexus_url"]
        == "https://www.nexusmods.com/cyberpunk2077/mods/107?tab=files&file_id=9001"
    )


@respx.mock
def test_free_from_mod_returns_files_url(client):
    _setup(client)
    _mock_validate(False)
    _mock_one_main_file()
    r = client.post(f"{G}/from-mod", json={"nexus_mod_id": 107})
    assert r.json()["requires_nxm"] is True
    assert r.json()["nexus_url"] == "https://www.nexusmods.com/cyberpunk2077/mods/107?tab=files"
