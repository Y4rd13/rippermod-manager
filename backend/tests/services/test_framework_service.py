"""Tests for the framework monitor service."""

import httpx
import pytest

from rippermod_manager.services import framework_service as svc


class _StubGQL:
    def __init__(self, result=None, exc=None):
        self._result = result or {}
        self._exc = exc

    async def batch_mods(self, domain, ids):
        if self._exc:
            raise self._exc
        return self._result


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.26.2", "1.26.2"),
        ("v1.37.1 [HEAD]", "1.37.1"),
        ("1.26.2.2601281547", "1.26.2.2601281547"),
        ("v2.0", "2.0"),
        (None, None),
        ("", None),
        ("garbage", None),
    ],
)
def test_clean_semver(raw, expected):
    assert svc._clean_semver(raw) == expected


class TestDetect:
    def test_present_missing_and_versionless(self, tmp_path, monkeypatch):
        (tmp_path / "red4ext").mkdir()
        (tmp_path / "red4ext" / "RED4ext.dll").write_bytes(b"x")
        (tmp_path / "engine" / "tools").mkdir(parents=True)
        (tmp_path / "engine" / "tools" / "scc.exe").write_bytes(b"x")
        monkeypatch.setattr(svc, "_read_pe_version", lambda p: "1.29.1")

        out = {d["key"]: d for d in svc.detect_frameworks(str(tmp_path))}

        # PE framework present → version read
        assert out["red4ext"]["installed"] is True
        assert out["red4ext"]["version"] == "1.29.1"
        assert out["red4ext"]["version_known"] is True
        assert out["red4ext"]["nexus_mod_id"] == 2380

        # redscript present but version_kind "none" → never reads a version
        assert out["redscript"]["installed"] is True
        assert out["redscript"]["version"] is None
        assert out["redscript"]["version_known"] is False

        # not installed
        assert out["archivexl"]["installed"] is False
        assert out["archivexl"]["version"] is None

    def test_all_six_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_read_pe_version", lambda p: "9.9.9")
        from rippermod_manager.constants import FRAMEWORKS

        for fw in FRAMEWORKS:
            marker = tmp_path.joinpath(*fw["marker"].split("/"))
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(b"x")

        out = svc.detect_frameworks(str(tmp_path))
        assert len(out) == 6
        assert all(d["installed"] for d in out)


class TestFetchLatest:
    async def test_extracts_versions(self):
        gql = _StubGQL({2380: {"version": "1.30.0"}, 4198: {"version": "1.27.0"}})
        out = await svc.fetch_latest_versions("cyberpunk2077", gql, [2380, 4198])
        assert out == {2380: "1.30.0", 4198: "1.27.0"}

    async def test_skips_blank_versions(self):
        gql = _StubGQL({2380: {"version": ""}, 4198: {}})
        assert await svc.fetch_latest_versions("cyberpunk2077", gql, [2380, 4198]) == {}

    async def test_best_effort_on_http_error(self):
        gql = _StubGQL(exc=httpx.HTTPError("boom"))
        assert await svc.fetch_latest_versions("cyberpunk2077", gql, [2380]) == {}

    async def test_empty_ids_no_call(self):
        gql = _StubGQL(exc=AssertionError("should not be called"))
        assert await svc.fetch_latest_versions("cyberpunk2077", gql, []) == {}
