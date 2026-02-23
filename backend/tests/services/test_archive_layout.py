"""Tests for archive layout detection (root-folder stripping and FOMOD flagging)."""

from __future__ import annotations

from dataclasses import dataclass

from chat_nexus_mod_manager.services.archive_layout import (
    ArchiveLayout,
    LayoutResult,
    detect_layout,
    known_roots_for_game,
)


@dataclass
class FakeEntry:
    filename: str
    is_dir: bool = False


# ---------------------------------------------------------------------------
# known_roots_for_game
# ---------------------------------------------------------------------------


class TestKnownRootsForGame:
    def test_cyberpunk_returns_expected_roots(self) -> None:
        roots = known_roots_for_game("cyberpunk2077")
        assert roots == {"archive", "bin", "red4ext", "r6", "mods"}

    def test_unknown_game_returns_empty(self) -> None:
        assert known_roots_for_game("unknowngame") == set()


# ---------------------------------------------------------------------------
# detect_layout — STANDARD
# ---------------------------------------------------------------------------


CP_ROOTS = {"archive", "bin", "red4ext", "r6", "mods"}


class TestStandard:
    def test_known_root_at_top_level(self) -> None:
        entries = [FakeEntry("archive/pc/mod/foo.archive")]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.STANDARD)

    def test_case_insensitive_known_root(self) -> None:
        entries = [FakeEntry("Archive/pc/mod/bar.archive")]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.STANDARD)

    def test_multiple_known_roots(self) -> None:
        entries = [
            FakeEntry("archive/pc/mod/a.archive"),
            FakeEntry("bin/x64/plugins/foo.dll"),
            FakeEntry("r6/scripts/init.reds"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.STANDARD)


# ---------------------------------------------------------------------------
# detect_layout — WRAPPED
# ---------------------------------------------------------------------------


class TestWrapped:
    def test_single_wrapper_with_known_second_level(self) -> None:
        entries = [
            FakeEntry("Drive-In Theater/", is_dir=True),
            FakeEntry("Drive-In Theater/archive/pc/mod/foo.archive"),
            FakeEntry("Drive-In Theater/archive/pc/mod/bar.archive"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result.layout == ArchiveLayout.WRAPPED
        assert result.strip_prefix == "Drive-In Theater"

    def test_strip_prefix_preserves_original_case(self) -> None:
        entries = [
            FakeEntry("MyMod/bin/x64/plugins/test.dll"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result.layout == ArchiveLayout.WRAPPED
        assert result.strip_prefix == "MyMod"

    def test_wrapper_with_multiple_known_second_levels(self) -> None:
        entries = [
            FakeEntry("CoolMod/archive/pc/mod/a.archive"),
            FakeEntry("CoolMod/r6/scripts/init.reds"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result.layout == ArchiveLayout.WRAPPED
        assert result.strip_prefix == "CoolMod"


# ---------------------------------------------------------------------------
# detect_layout — FOMOD
# ---------------------------------------------------------------------------


class TestFomod:
    def test_fomod_config_at_root(self) -> None:
        entries = [
            FakeEntry("fomod/ModuleConfig.xml"),
            FakeEntry("fomod/info.xml"),
            FakeEntry("Option A/archive/pc/mod/a.archive"),
            FakeEntry("Option B/archive/pc/mod/b.archive"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.FOMOD)

    def test_fomod_config_inside_wrapper(self) -> None:
        entries = [
            FakeEntry("MyMod/fomod/ModuleConfig.xml"),
            FakeEntry("MyMod/Option A/archive/pc/mod/a.archive"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.FOMOD)

    def test_fomod_config_case_insensitive(self) -> None:
        entries = [FakeEntry("FOMOD/MODULECONFIG.XML")]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.FOMOD)

    def test_info_xml_alone_is_not_fomod(self) -> None:
        entries = [
            FakeEntry("fomod/info.xml"),
            FakeEntry("archive/pc/mod/a.archive"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        # info.xml alone does NOT trigger FOMOD; should be STANDARD
        assert result.layout == ArchiveLayout.STANDARD

    def test_fomod_takes_precedence_over_standard(self) -> None:
        """FOMOD check runs after STANDARD, but FOMOD archives typically
        don't have known roots at top level. When fomod/ is present alongside
        non-root dirs, it should be flagged."""
        entries = [
            FakeEntry("fomod/ModuleConfig.xml"),
            FakeEntry("variant-a/archive/pc/mod/a.archive"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result.layout == ArchiveLayout.FOMOD


# ---------------------------------------------------------------------------
# detect_layout — UNKNOWN
# ---------------------------------------------------------------------------


class TestUnknown:
    def test_empty_archive(self) -> None:
        result = detect_layout([], CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.UNKNOWN)

    def test_only_dirs(self) -> None:
        entries = [FakeEntry("somedir/", is_dir=True)]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.UNKNOWN)

    def test_two_wrapper_folders(self) -> None:
        entries = [
            FakeEntry("FolderA/archive/pc/mod/a.archive"),
            FakeEntry("FolderB/archive/pc/mod/b.archive"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.UNKNOWN)

    def test_loose_file_plus_wrapper(self) -> None:
        entries = [
            FakeEntry("readme.txt"),
            FakeEntry("MyMod/archive/pc/mod/a.archive"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        # Has a root-level file + a wrapper dir → not a clean wrapper
        assert result == LayoutResult(layout=ArchiveLayout.UNKNOWN)

    def test_no_known_second_level(self) -> None:
        entries = [
            FakeEntry("Wrapper/textures/foo.dds"),
            FakeEntry("Wrapper/meshes/bar.mesh"),
        ]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.UNKNOWN)

    def test_no_known_roots_provided(self) -> None:
        entries = [FakeEntry("archive/pc/mod/a.archive")]
        result = detect_layout(entries, set())
        assert result == LayoutResult(layout=ArchiveLayout.UNKNOWN)

    def test_backslash_paths_normalised(self) -> None:
        entries = [FakeEntry("archive\\pc\\mod\\a.archive")]
        result = detect_layout(entries, CP_ROOTS)
        assert result == LayoutResult(layout=ArchiveLayout.STANDARD)
