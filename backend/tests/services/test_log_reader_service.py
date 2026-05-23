"""Tests for the mod error reader (log parsing)."""

import os
import time

from rippermod_manager.services import log_reader_service as svc


def _write(base, rel, lines):
    path = base.joinpath(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


class TestParsers:
    def test_spdlog(self):
        assert svc._match(svc._SPDLOG_RE, "[2026-05-18 18:23:11.921] [34060] [error] boom") == (
            "error",
            "2026-05-18 18:23:11.921",
            "boom",
        )
        # the 2nd bracket may be a logger name instead of a pid
        assert svc._match(svc._SPDLOG_RE, "[2026-05-18 18:22:47.544] [RED4ext] [info] hi") == (
            "info",
            "2026-05-18 18:22:47.544",
            "hi",
        )
        assert svc._match(svc._SPDLOG_RE, "not a log line") is None

    def test_cet(self):
        line = "[2026-03-09 17:53:03 UTC-03:00] [warning] [Foo::Bar()] [24668] careful"
        assert svc._match(svc._CET_RE, line) == (
            "warning",
            "2026-03-09 17:53:03 UTC-03:00",
            "careful",
        )

    def test_redscript(self):
        line = "[ERROR - Mon, 18 May 2026 18:23:25 -0400] type mismatch in Foo.reds"
        assert svc._match(svc._REDSCRIPT_RE, line) == (
            "error",
            "Mon, 18 May 2026 18:23:25 -0400",
            "type mismatch in Foo.reds",
        )


class TestReadLogErrors:
    def test_filters_info_keeps_error_and_warning(self, tmp_path):
        _write(
            tmp_path,
            "red4ext/logs/red4ext-1.log",
            [
                "[2026-05-18 18:22:47.544] [RED4ext] [info] starting",
                "[2026-05-18 18:22:48.000] [RED4ext] [error] plugin failed to load",
                "[2026-05-18 18:22:49.000] [RED4ext] [warning] deprecated thing",
            ],
        )
        _write(
            tmp_path,
            "r6/logs/redscript_rCURRENT.log",
            [
                "[INFO - Mon, 18 May 2026] Compiling",
                "[ERROR - Mon, 18 May 2026] type mismatch in Foo.reds",
            ],
        )
        out = svc.read_log_errors(str(tmp_path))
        assert all(e["level"] in ("error", "warning") for e in out)
        pairs = {(e["source"], e["level"], e["message"]) for e in out}
        assert ("RED4ext", "error", "plugin failed to load") in pairs
        assert ("RED4ext", "warning", "deprecated thing") in pairs
        assert ("redscript", "error", "type mismatch in Foo.reds") in pairs
        assert all(e["mod_name"] is None for e in out)

    def test_glob_picks_latest_red4ext_log(self, tmp_path):
        old = "[2026-01-01 00:00:00.000] [n] [error] old error"
        new = "[2026-05-01 00:00:00.000] [n] [error] new error"
        _write(tmp_path, "red4ext/logs/red4ext-old.log", [old])
        _write(tmp_path, "red4ext/logs/red4ext-new.log", [new])
        now = time.time()
        os.utime(tmp_path / "red4ext/logs/red4ext-old.log", (now - 100, now - 100))
        os.utime(tmp_path / "red4ext/logs/red4ext-new.log", (now, now))
        out = svc.read_log_errors(str(tmp_path))
        msgs = [e["message"] for e in out if e["source"] == "RED4ext"]
        assert "new error" in msgs
        assert "old error" not in msgs

    def test_tolerant_skips_unparseable_lines(self, tmp_path):
        _write(
            tmp_path,
            "red4ext/plugins/ArchiveXL/ArchiveXL.log",
            [
                "garbage with no format",
                "[2026-05-18 18:23:11.921] [34060] [error] real error",
                "more garbage",
            ],
        )
        out = svc.read_log_errors(str(tmp_path))
        assert len(out) == 1
        assert out[0]["source"] == "ArchiveXL"
        assert out[0]["message"] == "real error"

    def test_no_logs_returns_empty(self, tmp_path):
        assert svc.read_log_errors(str(tmp_path)) == []

    def test_caps_per_source(self, tmp_path):
        lines = [f"[2026-05-18 18:23:11.921] [n] [error] err {i}" for i in range(120)]
        _write(tmp_path, "red4ext/plugins/ArchiveXL/ArchiveXL.log", lines)
        archivexl = [e for e in svc.read_log_errors(str(tmp_path)) if e["source"] == "ArchiveXL"]
        assert len(archivexl) == svc._MAX_PER_SOURCE

    def test_keeps_spdlog_critical_as_error(self, tmp_path):
        # spdlog's "critical" is the most severe level — surface it, don't drop it.
        line = "[2026-05-18 18:22:48.000] [n] [critical] hard crash"
        _write(tmp_path, "red4ext/logs/red4ext-1.log", [line])
        out = svc.read_log_errors(str(tmp_path))
        assert len(out) == 1
        assert out[0]["level"] == "error"
        assert out[0]["message"] == "hard crash"


class TestAttribution:
    def test_candidate_redscript_bare_path(self):
        # a bare path in a redscript error is relative to r6/scripts
        assert (
            svc._candidate_path("redscript", "type mismatch in MyMod/Foo.reds", None, "")
            == "r6/scripts/mymod/foo.reds"
        )

    def test_candidate_redscript_absolute_path(self):
        cand = svc._candidate_path(
            "redscript",
            r"error in G:\games\cp2077\red4ext\plugins\ArchiveXL\Scripts\ArchiveXL.reds",
            None,
            "g:/games/cp2077",
        )
        assert cand == "red4ext/plugins/archivexl/scripts/archivexl.reds"

    def test_candidate_red4ext_dll(self):
        assert (
            svc._candidate_path(
                "RED4ext",
                r"Loading plugin from 'red4ext\plugins\Codeware\Codeware.dll'...",
                None,
                "",
            )
            == "red4ext/plugins/codeware/codeware.dll"
        )

    def test_candidate_cet_mods_folder(self):
        assert (
            svc._candidate_path("CET", r"loaded ('mods\AppearanceMenuMod')", None, "")
            == "bin/x64/plugins/cyber_engine_tweaks/mods/appearancemenumod"
        )

    def test_candidate_archivexl_depot_path_is_unattributable(self):
        # ArchiveXL carries virtual depot paths, not on-disk paths -> no candidate
        assert (
            svc._candidate_path("ArchiveXL", 'Factory "mod\\foo\\items.csv" missing', None, "")
            is None
        )

    def test_candidate_tweakxl_uses_last_reading(self):
        assert (
            svc._candidate_path("TweakXL", "Vendors.x: Unknown property foo.", "mytweak.yaml", "")
            == "r6/tweaks/mytweak.yaml"
        )
        # without a preceding "Reading" line there's nothing to attribute to
        assert svc._candidate_path("TweakXL", "Vendors.x: Unknown property foo.", None, "") is None

    def test_attribution_sets_mod_name_on_owned_path(self, tmp_path):
        _write(
            tmp_path,
            "r6/logs/redscript_rCURRENT.log",
            ["[ERROR - Mon, 18 May 2026] type mismatch in MyMod/Foo.reds"],
        )
        out = svc.read_log_errors(str(tmp_path), {"r6/scripts/mymod/foo.reds": "My Mod"})
        assert len(out) == 1
        assert out[0]["mod_name"] == "My Mod"

    def test_attribution_miss_leaves_none(self, tmp_path):
        _write(
            tmp_path,
            "r6/logs/redscript_rCURRENT.log",
            ["[ERROR - Mon, 18 May 2026] type mismatch in Other/Bar.reds"],
        )
        out = svc.read_log_errors(str(tmp_path), {"r6/scripts/mymod/foo.reds": "My Mod"})
        assert out[0]["mod_name"] is None

    def test_tweakxl_stateful_attribution(self, tmp_path):
        _write(
            tmp_path,
            "red4ext/plugins/TweakXL/TweakXL.log",
            [
                '[2026-05-18 18:22:47.544] [n] [info] Reading "MyTweak.yaml"...',
                "[2026-05-18 18:22:48.000] [n] [error] Vendors.x: Unknown property foo.",
            ],
        )
        out = svc.read_log_errors(str(tmp_path), {"r6/tweaks/mytweak.yaml": "Tweak Mod"})
        tweak = [e for e in out if e["source"] == "TweakXL"]
        assert len(tweak) == 1
        assert tweak[0]["mod_name"] == "Tweak Mod"

    def test_cet_attribution_via_dir_prefix(self, tmp_path):
        _write(
            tmp_path,
            "bin/x64/plugins/cyber_engine_tweaks/cyber_engine_tweaks.log",
            ["[2026-03-09 17:53:03 UTC-03:00] [error] [F()] [123] init failed in mods\\MyCetMod"],
        )
        owners = {"bin/x64/plugins/cyber_engine_tweaks/mods/mycetmod/init.lua": "My CET Mod"}
        out = svc.read_log_errors(str(tmp_path), owners)
        cet = [e for e in out if e["source"] == "CET"]
        assert len(cet) == 1
        assert cet[0]["mod_name"] == "My CET Mod"
