import pytest

from rippermod_manager.matching.filename_parser import (
    ParsedFilename,
    is_newer_version,
    parse_mod_filename,
    parse_version,
)


class TestParseModFilename:
    def test_nexus_format(self):
        # Full Nexus download format: ModName-{id}-{version}-{timestamp}.zip
        result = parse_mod_filename("CET-107-1-37-1-1759193708.zip")
        assert result.nexus_mod_id == 107
        assert result.version == "1.37.1"
        assert result.upload_timestamp == 1759193708

    def test_simple_format(self):
        # Simple id-name format: {id}-ModName.7z
        result = parse_mod_filename("107-CyberEngineTweaks.7z")
        assert result.nexus_mod_id == 107
        assert result.name == "CyberEngineTweaks"
        assert result.version is None
        assert result.upload_timestamp is None

    def test_plain_format(self):
        # Bare filename with no metadata
        result = parse_mod_filename("SomeMod.zip")
        assert result.nexus_mod_id is None
        assert result.name == "SomeMod"
        assert result.version is None
        assert result.upload_timestamp is None

    def test_version_with_v_prefix(self):
        result = parse_mod_filename("Mod-123-v2-0-0-1234567890.zip")
        assert result.nexus_mod_id == 123
        assert result.upload_timestamp == 1234567890

    def test_no_extension(self):
        # Files without an extension should still parse
        result = parse_mod_filename("ModName-456-1-0-1234567890")
        assert result.nexus_mod_id == 456
        assert result.upload_timestamp == 1234567890

    def test_nexus_format_name_extracted(self):
        result = parse_mod_filename("Enhanced-Weather-12345-2-0-0-1750000000.zip")
        assert result.nexus_mod_id == 12345
        assert "Enhanced" in result.name or result.name  # name is non-empty

    def test_plain_format_with_spaces_in_name(self):
        result = parse_mod_filename("My Cool Mod.zip")
        assert result.nexus_mod_id is None
        assert result.name == "My Cool Mod"

    def test_simple_format_underscore_separator(self):
        result = parse_mod_filename("999_SomeMod.rar")
        assert result.nexus_mod_id == 999
        assert result.name == "SomeMod"

    def test_returns_parsed_filename_dataclass(self):
        result = parse_mod_filename("anything.zip")
        assert isinstance(result, ParsedFilename)

    def test_nexus_version_dots_converted(self):
        # Dashes in version segment become dots: "1-37-1" -> "1.37.1"
        result = parse_mod_filename("CET-107-1-37-1-1759193708.zip")
        assert "." in result.version

    @pytest.mark.parametrize(
        "filename,expected_id",
        [
            ("Mod-100-1-0-0-1700000000.zip", 100),
            ("Mod-999999-2-5-0-1800000000.7z", 999999),
            ("1-ModAlpha.zip", 1),
        ],
    )
    def test_nexus_id_extraction_parametrized(self, filename, expected_id):
        result = parse_mod_filename(filename)
        assert result.nexus_mod_id == expected_id


class TestParseVersion:
    def test_standard_semver(self):
        parts = parse_version("1.2.3")
        assert parts == [(1, ""), (2, ""), (3, "")]

    def test_version_with_beta_suffix(self):
        parts = parse_version("1.0.0-beta")
        assert parts[0] == (1, "")
        assert any(p[1] == "beta" or "beta" in p[1] for p in parts)

    def test_empty_string_returns_empty_list(self):
        assert parse_version("") == []

    def test_single_digit(self):
        parts = parse_version("2")
        assert parts == [(2, "")]

    def test_version_with_alpha_suffix_on_segment(self):
        parts = parse_version("2.1.1a")
        # Last segment should contain numeric and alpha portion
        assert len(parts) == 3

    def test_non_numeric_segment(self):
        # Purely textual segments get numeric value -1
        parts = parse_version("beta")
        assert len(parts) == 1
        assert parts[0][0] == -1

    def test_version_with_underscore_separator(self):
        parts = parse_version("1_0_0")
        assert len(parts) == 3

    def test_two_part_version(self):
        parts = parse_version("1.0")
        assert parts == [(1, ""), (0, "")]


class TestIsNewerVersion:
    def test_newer_patch(self):
        assert is_newer_version("1.2.3", "1.2.2") is True

    def test_older_patch(self):
        assert is_newer_version("1.2.2", "1.2.3") is False

    def test_numeric_major_beats_lexicographic(self):
        # 0.15.0 > 0.2.0 numerically, but "15" < "2" lexicographically
        assert is_newer_version("0.15.0", "0.2.0") is True

    def test_equal_versions_returns_false(self):
        assert is_newer_version("1.0.0", "1.0.0") is False

    def test_newer_major(self):
        assert is_newer_version("2.0.0", "1.9.9") is True

    def test_older_major(self):
        assert is_newer_version("1.0.0", "2.0.0") is False

    def test_release_beats_prerelease(self):
        # "1.0" (empty suffix) should beat "1.0-beta" (non-empty suffix)
        assert is_newer_version("1.0", "1.0-beta") is True

    def test_prerelease_does_not_beat_release(self):
        assert is_newer_version("1.0-beta", "1.0") is False

    def test_both_empty_returns_false(self):
        # Equal empty-version strings: not newer
        assert is_newer_version("", "") is False

    def test_newer_minor(self):
        assert is_newer_version("1.3.0", "1.2.9") is True

    @pytest.mark.parametrize(
        "latest,installed,expected",
        [
            ("2.0.0", "1.0.0", True),
            ("1.0.0", "1.0.0", False),
            ("0.9.9", "1.0.0", False),
            ("0.15.0", "0.2.0", True),
            ("1.0", "1.0-alpha", True),
        ],
    )
    def test_parametrized_comparisons(self, latest, installed, expected):
        assert is_newer_version(latest, installed) is expected
