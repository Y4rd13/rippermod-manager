from chat_nexus_mod_manager.matching.grouper import (
    group_mod_files,
    normalize_name,
    tokenize,
)
from chat_nexus_mod_manager.models.mod import ModFile


def _file(name: str, folder: str = "mods") -> ModFile:
    return ModFile(filename=name, file_path=f"{folder}/{name}", source_folder=folder)


class TestNormalizeName:
    def test_strips_extension(self):
        assert normalize_name("mymod.archive") == "mymod"

    def test_removes_version(self):
        assert "1.0" not in normalize_name("mymod_v1.0.2.archive")

    def test_collapses_separators(self):
        result = normalize_name("my__mod--name.archive")
        assert "  " not in result
        assert "__" not in result

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_lowercases(self):
        assert normalize_name("MyMod.archive") == "mymod"


class TestTokenize:
    def test_splits_words(self):
        assert tokenize("hello world") == ["hello", "world"]

    def test_filters_single_chars(self):
        assert tokenize("a big mod") == ["big", "mod"]

    def test_empty_string(self):
        assert tokenize("") == []


class TestGroupModFiles:
    def test_empty_list(self):
        assert group_mod_files([]) == []

    def test_single_file(self):
        result = group_mod_files([_file("cool_mod.archive")])
        assert len(result) == 1
        _name, files, confidence = result[0]
        assert len(files) == 1
        assert confidence == 1.0

    def test_similar_names_cluster(self):
        files = [
            _file("enhanced_weather_part1.archive"),
            _file("enhanced_weather_part2.archive"),
        ]
        result = group_mod_files(files)
        assert len(result) == 1
        _, grouped, _ = result[0]
        assert len(grouped) == 2

    def test_dissimilar_files_separate(self):
        files = [
            _file("cyberpunk_hd_textures.archive"),
            _file("romance_expanded_mod.lua"),
        ]
        result = group_mod_files(files)
        assert len(result) >= 2

    def test_title_cased_names(self):
        files = [
            _file("weather_enhanced_part1.archive"),
            _file("weather_enhanced_part2.archive"),
        ]
        result = group_mod_files(files)
        name, _, _ = result[0]
        assert name == name.title()
