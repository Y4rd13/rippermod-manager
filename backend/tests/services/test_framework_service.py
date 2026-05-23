"""Tests for the framework monitor service."""

import httpx
import pytest

from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusModMeta
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

    async def test_normalizes_nexus_version(self):
        # A Nexus "v"-prefixed version is cleaned like the on-disk one (no "vv1.30.0").
        gql = _StubGQL({2380: {"version": "v1.30.0"}})
        assert await svc.fetch_latest_versions("cyberpunk2077", gql, [2380]) == {2380: "1.30.0"}

    async def test_keeps_unparseable_version_raw(self):
        # Non-semver versions fall back to the raw string rather than being dropped.
        gql = _StubGQL({2380: {"version": "2025-build-7"}})
        assert await svc.fetch_latest_versions("cyberpunk2077", gql, [2380]) == {
            2380: "2025-build-7"
        }

    async def test_skips_blank_versions(self):
        gql = _StubGQL({2380: {"version": ""}, 4198: {}})
        assert await svc.fetch_latest_versions("cyberpunk2077", gql, [2380, 4198]) == {}

    async def test_best_effort_on_http_error(self):
        gql = _StubGQL(exc=httpx.HTTPError("boom"))
        assert await svc.fetch_latest_versions("cyberpunk2077", gql, [2380]) == {}

    async def test_empty_ids_no_call(self):
        gql = _StubGQL(exc=AssertionError("should not be called"))
        assert await svc.fetch_latest_versions("cyberpunk2077", gql, []) == {}


class TestManagerState:
    def test_manager_status_resolution(self):
        assert svc.manager_status(True, None) == "active"
        assert svc.manager_status(True, True) == "active"
        assert svc.manager_status(False, True) == "deploy_pending"
        assert svc.manager_status(False, False) == "disabled"
        assert svc.manager_status(False, None) == "not_installed"

    def test_framework_manager_state_aggregates(self, session, make_game):
        game = make_game(name="A")
        other = make_game(name="B", install_path="/games/b")
        # RED4ext (2380): two rows — one disabled, one enabled → enabled wins.
        session.add(InstalledMod(game_id=game.id, name="r4-a", nexus_mod_id=2380, disabled=True))
        session.add(InstalledMod(game_id=game.id, name="r4-b", nexus_mod_id=2380, disabled=False))
        # CET (107): single row, disabled.
        session.add(InstalledMod(game_id=game.id, name="cet", nexus_mod_id=107, disabled=True))
        # A non-framework mod and a framework on another game are both ignored.
        session.add(InstalledMod(game_id=game.id, name="misc", nexus_mod_id=99999, disabled=False))
        session.add(InstalledMod(game_id=other.id, name="txl", nexus_mod_id=4197, disabled=False))
        session.commit()

        state = svc.framework_manager_state(session, game.id)
        assert state[2380] is True  # any-enabled wins over a disabled sibling
        assert state[107] is False  # all matching rows disabled
        assert 99999 not in state  # not a framework id
        assert 4197 not in state  # belongs to another game


class TestCachedLatest:
    def test_reads_and_cleans(self, session):
        session.add(NexusModMeta(nexus_mod_id=2380, version="v1.30.0"))
        session.add(NexusModMeta(nexus_mod_id=4198, version="1.27.0"))
        session.add(NexusModMeta(nexus_mod_id=107, version=""))  # blank → skipped
        session.commit()

        out = svc.cached_latest_versions(session, [2380, 4198, 107, 1511])
        assert out == {2380: "1.30.0", 4198: "1.27.0"}

    def test_empty_ids(self, session):
        assert svc.cached_latest_versions(session, []) == {}
