"""Tests for TweakXL conflict analyzer."""

from rippermod_manager.schemas.tweakxl import (
    ConflictSeverity,
    TweakEntry,
    TweakOperation,
)
from rippermod_manager.services.tweakxl_conflict_analyzer import analyze_conflicts

_SEVERITY_ORDER = {
    ConflictSeverity.HIGH: 0,
    ConflictSeverity.MEDIUM: 1,
    ConflictSeverity.LOW: 2,
}


def _entry(
    key: str,
    op: TweakOperation,
    value: str,
    mod_id: str = "mod-a",
    source_file: str = "r6/tweaks/test.yaml",
) -> TweakEntry:
    return TweakEntry(
        key=key,
        operation=op,
        value=value,
        source_file=source_file,
        mod_id=mod_id,
    )


class TestSetVsSetConflicts:
    def test_different_values_is_high(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.quality", TweakOperation.SET, "Legendary", "mod-a")],
                "mod-b": [_entry("Items.Foo.quality", TweakOperation.SET, "Common", "mod-b")],
            }
        )
        assert result.total_conflicts == 1
        assert result.conflicts[0].severity == ConflictSeverity.HIGH
        assert "mod-a" in result.mods_analyzed
        assert "mod-b" in result.mods_analyzed

    def test_same_values_is_low(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.quality", TweakOperation.SET, "Legendary", "mod-a")],
                "mod-b": [_entry("Items.Foo.quality", TweakOperation.SET, "Legendary", "mod-b")],
            }
        )
        assert result.total_conflicts == 1
        assert result.conflicts[0].severity == ConflictSeverity.LOW

    def test_different_keys_no_conflict(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.quality", TweakOperation.SET, "Legendary", "mod-a")],
                "mod-b": [_entry("Items.Bar.quality", TweakOperation.SET, "Common", "mod-b")],
            }
        )
        assert result.total_conflicts == 0

    def test_same_mod_no_self_conflict(self):
        result = analyze_conflicts(
            {
                "mod-a": [
                    _entry("Items.Foo.quality", TweakOperation.SET, "Legendary", "mod-a"),
                    _entry("Items.Foo.quality", TweakOperation.SET, "Common", "mod-a"),
                ],
            }
        )
        assert result.total_conflicts == 0


class TestAppendRemoveConflicts:
    def test_append_vs_remove_same_value_is_medium(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.tags", TweakOperation.APPEND, "TagA", "mod-a")],
                "mod-b": [_entry("Items.Foo.tags", TweakOperation.REMOVE, "TagA", "mod-b")],
            }
        )
        assert result.total_conflicts == 1
        assert result.conflicts[0].severity == ConflictSeverity.MEDIUM

    def test_append_vs_remove_different_values_no_conflict(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.tags", TweakOperation.APPEND, "TagA", "mod-a")],
                "mod-b": [_entry("Items.Foo.tags", TweakOperation.REMOVE, "TagB", "mod-b")],
            }
        )
        assert result.total_conflicts == 0

    def test_remove_vs_append_same_value_is_medium(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.tags", TweakOperation.REMOVE, "TagA", "mod-a")],
                "mod-b": [_entry("Items.Foo.tags", TweakOperation.APPEND, "TagA", "mod-b")],
            }
        )
        assert result.total_conflicts == 1
        assert result.conflicts[0].severity == ConflictSeverity.MEDIUM


class TestSetPlusArrayConflicts:
    def test_set_vs_append_is_medium(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.tags", TweakOperation.SET, "NewValue", "mod-a")],
                "mod-b": [_entry("Items.Foo.tags", TweakOperation.APPEND, "ExtraTag", "mod-b")],
            }
        )
        assert result.total_conflicts == 1
        assert result.conflicts[0].severity == ConflictSeverity.MEDIUM

    def test_set_vs_remove_is_medium(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.tags", TweakOperation.SET, "Override", "mod-a")],
                "mod-b": [_entry("Items.Foo.tags", TweakOperation.REMOVE, "SomeThing", "mod-b")],
            }
        )
        assert result.total_conflicts == 1
        assert result.conflicts[0].severity == ConflictSeverity.MEDIUM


class TestCaseInsensitiveKeys:
    def test_keys_match_case_insensitively(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.Quality", TweakOperation.SET, "Legendary", "mod-a")],
                "mod-b": [_entry("items.foo.quality", TweakOperation.SET, "Common", "mod-b")],
            }
        )
        assert result.total_conflicts == 1
        assert result.conflicts[0].severity == ConflictSeverity.HIGH


class TestMultiModConflicts:
    def test_three_mods_pairwise(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.q", TweakOperation.SET, "A", "mod-a")],
                "mod-b": [_entry("Items.Foo.q", TweakOperation.SET, "B", "mod-b")],
                "mod-c": [_entry("Items.Foo.q", TweakOperation.SET, "C", "mod-c")],
            }
        )
        assert result.total_conflicts == 3
        assert all(c.severity == ConflictSeverity.HIGH for c in result.conflicts)


class TestNoConflicts:
    def test_single_mod(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.q", TweakOperation.SET, "A", "mod-a")],
            }
        )
        assert result.total_conflicts == 0

    def test_empty_input(self):
        result = analyze_conflicts({})
        assert result.total_conflicts == 0
        assert result.total_entries == 0

    def test_disjoint_keys(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.x", TweakOperation.SET, "1", "mod-a")],
                "mod-b": [_entry("Items.Bar.y", TweakOperation.SET, "2", "mod-b")],
            }
        )
        assert result.total_conflicts == 0

    def test_both_append_same_key_no_conflict(self):
        result = analyze_conflicts(
            {
                "mod-a": [_entry("Items.Foo.tags", TweakOperation.APPEND, "A", "mod-a")],
                "mod-b": [_entry("Items.Foo.tags", TweakOperation.APPEND, "B", "mod-b")],
            }
        )
        assert result.total_conflicts == 0


class TestResultMetadata:
    def test_total_entries_counted(self):
        result = analyze_conflicts(
            {
                "mod-a": [
                    _entry("X.a", TweakOperation.SET, "1", "mod-a"),
                    _entry("X.b", TweakOperation.SET, "2", "mod-a"),
                ],
                "mod-b": [_entry("X.a", TweakOperation.SET, "3", "mod-b")],
            }
        )
        assert result.total_entries == 3
        assert result.mods_analyzed == ["mod-a", "mod-b"]

    def test_conflicts_sorted_severity_descending(self):
        result = analyze_conflicts(
            {
                "mod-a": [
                    _entry("K.high", TweakOperation.SET, "A", "mod-a"),
                    _entry("K.low", TweakOperation.SET, "Same", "mod-a"),
                    _entry("K.med", TweakOperation.SET, "Over", "mod-a"),
                ],
                "mod-b": [
                    _entry("K.high", TweakOperation.SET, "B", "mod-b"),
                    _entry("K.low", TweakOperation.SET, "Same", "mod-b"),
                    _entry("K.med", TweakOperation.APPEND, "Extra", "mod-b"),
                ],
            }
        )
        severities = [c.severity for c in result.conflicts]
        assert severities == sorted(severities, key=lambda s: _SEVERITY_ORDER[s])
