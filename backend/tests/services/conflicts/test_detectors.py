"""Unit tests for individual conflict detectors."""

import pytest

from rippermod_manager.models.conflict import ConflictKind, Severity
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.conflicts.detectors import (
    ArchiveEntryDetector,
    RedscriptTargetDetector,
    TweakKeyDetector,
    _archive_entry_severity,
)


@pytest.fixture
def game_with_dir(session, tmp_path):
    """Create a game with a real filesystem directory."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    g = Game(name="DetectorTest", domain_name="cyberpunk2077", install_path=str(game_dir))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="r6/scripts"))
    session.add(GameModPath(game_id=g.id, relative_path="r6/tweaks"))
    session.commit()
    session.refresh(g)
    return g, game_dir


def _add_mod(session, game, name, files, *, disabled=False):
    """Helper to create an InstalledMod with files."""
    mod = InstalledMod(game_id=game.id, name=name, disabled=disabled)
    session.add(mod)
    session.flush()
    for rel_path in files:
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path=rel_path))
    session.commit()
    session.refresh(mod)
    _ = mod.files
    return mod


# ---------------------------------------------------------------------------
# Severity rules
# ---------------------------------------------------------------------------


class TestArchiveEntrySeverity:
    def test_high_for_archive_pc_mod(self):
        assert _archive_entry_severity("archive/pc/mod/base.archive") == Severity.high

    def test_high_for_bin_plugins(self):
        assert _archive_entry_severity("bin/x64/plugins/cyber.dll") == Severity.high

    def test_medium_for_r6_scripts(self):
        assert _archive_entry_severity("r6/scripts/mymod/init.reds") == Severity.medium

    def test_medium_for_r6_tweaks(self):
        assert _archive_entry_severity("r6/tweaks/mymod/config.yaml") == Severity.medium

    def test_medium_for_mods(self):
        assert _archive_entry_severity("mods/mymod/init.lua") == Severity.medium

    def test_low_for_other(self):
        assert _archive_entry_severity("readme.txt") == Severity.low

    def test_case_insensitive(self):
        assert _archive_entry_severity("Archive/PC/Mod/test.archive") == Severity.high


# ---------------------------------------------------------------------------
# ArchiveEntryDetector
# ---------------------------------------------------------------------------


class TestArchiveEntryDetector:
    def test_no_conflicts_when_no_overlap(self, session, game_with_dir):
        game, _ = game_with_dir
        mod_a = _add_mod(session, game, "A", ["a.txt"])
        mod_b = _add_mod(session, game, "B", ["b.txt"])

        detector = ArchiveEntryDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 0

    def test_detects_file_overlap(self, session, game_with_dir):
        game, _ = game_with_dir
        mod_a = _add_mod(session, game, "A", ["shared.txt"])
        mod_b = _add_mod(session, game, "B", ["shared.txt"])

        detector = ArchiveEntryDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 1
        assert evidence[0].key == "shared.txt"
        assert evidence[0].kind == ConflictKind.archive_entry

    def test_winner_is_last_mod(self, session, game_with_dir):
        game, _ = game_with_dir
        mod_a = _add_mod(session, game, "A", ["shared.txt"])
        mod_b = _add_mod(session, game, "B", ["shared.txt"])

        detector = ArchiveEntryDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert evidence[0].winner_mod_id == mod_b.id

    def test_high_severity_for_archive_path(self, session, game_with_dir):
        game, _ = game_with_dir
        path = "archive/pc/mod/basegame.archive"
        mod_a = _add_mod(session, game, "A", [path])
        mod_b = _add_mod(session, game, "B", [path])

        detector = ArchiveEntryDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 1
        assert evidence[0].severity == Severity.high

    def test_skips_disabled_mods(self, session, game_with_dir):
        game, _ = game_with_dir
        mod_a = _add_mod(session, game, "A", ["x.txt"])
        mod_b = _add_mod(session, game, "B", ["x.txt"], disabled=True)

        detector = ArchiveEntryDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 0

    def test_case_insensitive_path_matching(self, session, game_with_dir):
        game, _ = game_with_dir
        mod_a = _add_mod(session, game, "A", ["Mods/File.TXT"])
        mod_b = _add_mod(session, game, "B", ["mods/file.txt"])

        detector = ArchiveEntryDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 1

    def test_three_way_conflict(self, session, game_with_dir):
        game, _ = game_with_dir
        mod_a = _add_mod(session, game, "A", ["shared.dll"])
        mod_b = _add_mod(session, game, "B", ["shared.dll"])
        mod_c = _add_mod(session, game, "C", ["shared.dll"])

        detector = ArchiveEntryDetector()
        evidence = detector.detect(game, [mod_a, mod_b, mod_c], session)
        assert len(evidence) == 1
        mod_ids = [int(m) for m in evidence[0].mod_ids.split(",")]
        assert len(mod_ids) == 3


# ---------------------------------------------------------------------------
# RedscriptTargetDetector
# ---------------------------------------------------------------------------


class TestRedscriptTargetDetector:
    def test_detects_wrap_method_conflict(self, session, game_with_dir):
        game, game_dir = game_with_dir
        scripts = game_dir / "r6" / "scripts"

        dir_a = scripts / "mod_a"
        dir_a.mkdir(parents=True)
        (dir_a / "main.reds").write_text(
            "@wrapMethod(PlayerPuppet)\nprotected func OnAction() {\n}\n"
        )
        mod_a = _add_mod(session, game, "ScriptA", ["r6/scripts/mod_a/main.reds"])

        dir_b = scripts / "mod_b"
        dir_b.mkdir(parents=True)
        (dir_b / "main.reds").write_text("@wrapMethod(PlayerPuppet)\npublic func OnAction() {\n}\n")
        mod_b = _add_mod(session, game, "ScriptB", ["r6/scripts/mod_b/main.reds"])

        detector = RedscriptTargetDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 1
        assert evidence[0].key == "PlayerPuppet.OnAction"
        assert evidence[0].severity == Severity.high

    def test_no_conflict_on_different_methods(self, session, game_with_dir):
        game, game_dir = game_with_dir
        scripts = game_dir / "r6" / "scripts"

        d = scripts / "a"
        d.mkdir(parents=True)
        (d / "a.reds").write_text("@wrapMethod(Foo)\nfunc Bar() {}\n")
        mod_a = _add_mod(session, game, "A", ["r6/scripts/a/a.reds"])

        d2 = scripts / "b"
        d2.mkdir(parents=True)
        (d2 / "b.reds").write_text("@wrapMethod(Foo)\nfunc Baz() {}\n")
        mod_b = _add_mod(session, game, "B", ["r6/scripts/b/b.reds"])

        detector = RedscriptTargetDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 0

    def test_addmethod_is_medium_severity(self, session, game_with_dir):
        game, game_dir = game_with_dir
        scripts = game_dir / "r6" / "scripts"

        d1 = scripts / "m1"
        d1.mkdir(parents=True)
        (d1 / "x.reds").write_text("@addMethod(Vehicle)\nfunc GetSpeed() {}\n")
        mod_a = _add_mod(session, game, "A", ["r6/scripts/m1/x.reds"])

        d2 = scripts / "m2"
        d2.mkdir(parents=True)
        (d2 / "x.reds").write_text("@addMethod(Vehicle)\nfunc GetSpeed() {}\n")
        mod_b = _add_mod(session, game, "B", ["r6/scripts/m2/x.reds"])

        detector = RedscriptTargetDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 1
        assert evidence[0].severity == Severity.medium

    def test_missing_file_is_skipped(self, session, game_with_dir):
        game, _ = game_with_dir
        mod_a = _add_mod(session, game, "A", ["r6/scripts/missing/main.reds"])

        detector = RedscriptTargetDetector()
        evidence = detector.detect(game, [mod_a], session)
        assert len(evidence) == 0


# ---------------------------------------------------------------------------
# TweakKeyDetector
# ---------------------------------------------------------------------------


class TestTweakKeyDetector:
    def test_detects_same_tweak_key(self, session, game_with_dir):
        game, game_dir = game_with_dir
        tweaks = game_dir / "r6" / "tweaks"

        ta = tweaks / "mod_a"
        ta.mkdir(parents=True)
        (ta / "config.yaml").write_text("Items.SomeWeapon.damage:\n  value: 100\n")
        mod_a = _add_mod(session, game, "TweakA", ["r6/tweaks/mod_a/config.yaml"])

        tb = tweaks / "mod_b"
        tb.mkdir(parents=True)
        (tb / "config.yaml").write_text("Items.SomeWeapon.damage:\n  value: 200\n")
        mod_b = _add_mod(session, game, "TweakB", ["r6/tweaks/mod_b/config.yaml"])

        detector = TweakKeyDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 1
        assert evidence[0].key == "Items.SomeWeapon.damage"
        assert evidence[0].severity == Severity.medium

    def test_append_keys_are_low_severity(self, session, game_with_dir):
        game, game_dir = game_with_dir
        tweaks = game_dir / "r6" / "tweaks"

        ta = tweaks / "a"
        ta.mkdir(parents=True)
        (ta / "t.yaml").write_text("Items.MyList.$append:\n  - item1\n")
        mod_a = _add_mod(session, game, "A", ["r6/tweaks/a/t.yaml"])

        tb = tweaks / "b"
        tb.mkdir(parents=True)
        (tb / "t.yaml").write_text("Items.MyList.$append:\n  - item2\n")
        mod_b = _add_mod(session, game, "B", ["r6/tweaks/b/t.yaml"])

        detector = TweakKeyDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 1
        assert evidence[0].severity == Severity.low

    def test_mixed_append_and_set_is_medium(self, session, game_with_dir):
        game, game_dir = game_with_dir
        tweaks = game_dir / "r6" / "tweaks"

        ta = tweaks / "a"
        ta.mkdir(parents=True)
        (ta / "t.yaml").write_text("Items.MyItem.value:\n  100\n")
        mod_a = _add_mod(session, game, "A", ["r6/tweaks/a/t.yaml"])

        tb = tweaks / "b"
        tb.mkdir(parents=True)
        (tb / "t.yaml").write_text("Items.MyItem.value.$append:\n  - extra\n")
        mod_b = _add_mod(session, game, "B", ["r6/tweaks/b/t.yaml"])

        detector = TweakKeyDetector()
        evidence = detector.detect(game, [mod_a, mod_b], session)
        assert len(evidence) == 1
        assert evidence[0].severity == Severity.medium

    def test_ignores_non_tweak_directory(self, session, game_with_dir):
        game, game_dir = game_with_dir
        other = game_dir / "mods"
        other.mkdir(parents=True)
        (other / "config.yaml").write_text("Items.Test.key:\n  val: 1\n")
        mod_a = _add_mod(session, game, "A", ["mods/config.yaml"])

        detector = TweakKeyDetector()
        evidence = detector.detect(game, [mod_a], session)
        assert len(evidence) == 0

    def test_missing_file_is_skipped(self, session, game_with_dir):
        game, _ = game_with_dir
        mod_a = _add_mod(session, game, "A", ["r6/tweaks/missing/config.yaml"])

        detector = TweakKeyDetector()
        evidence = detector.detect(game, [mod_a], session)
        assert len(evidence) == 0
