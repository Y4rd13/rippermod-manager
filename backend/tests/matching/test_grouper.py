from chat_nexus_mod_manager.matching.grouper import (
    group_mod_files,
    normalize_name,
)
from chat_nexus_mod_manager.models.mod import ModFile


def _file(name: str, folder: str = "mods", subfolder: str | None = None) -> ModFile:
    path = f"{folder}/{subfolder}/{name}" if subfolder else f"{folder}/{name}"
    return ModFile(filename=name, file_path=path, source_folder=folder)


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
        assert normalize_name("MyMod.archive") == "my mod"


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


class TestFolderAwareGrouping:
    def test_cet_mods_grouped_by_folder_not_filename(self):
        """CET mods with same init.lua should be grouped by folder name."""
        cet = "bin/x64/plugins/cyber_engine_tweaks/mods"
        files = [
            _file("init.lua", folder=cet, subfolder="AppearanceMenuMod"),
            _file("init.lua", folder=cet, subfolder="CyberCat"),
        ]
        result = group_mod_files(files)
        assert len(result) == 2
        names = {r[0] for r in result}
        assert names == {"Appearance Menu Mod", "Cyber Cat"}

    def test_folder_groups_have_confidence_one(self):
        files = [
            _file("init.lua", folder="mods", subfolder="ModA"),
            _file("utils.lua", folder="mods", subfolder="ModA"),
        ]
        result = group_mod_files(files)
        assert len(result) == 1
        name, grouped, confidence = result[0]
        assert name == "Mod A"
        assert len(grouped) == 2
        assert confidence == 1.0

    def test_mixed_folder_and_loose_files(self):
        """r6/scripts with folders + loose .reds should split correctly."""
        folder = "r6/scripts"
        files = [
            _file("main.reds", folder=folder, subfolder="Codeware"),
            _file("helpers.reds", folder=folder, subfolder="Codeware"),
            _file("standalone_tweak.reds", folder=folder),
        ]
        result = group_mod_files(files)
        folder_results = [r for r in result if r[2] == 1.0 and r[0] == "Codeware"]
        assert len(folder_results) == 1
        assert len(folder_results[0][1]) == 2
        loose_results = [r for r in result if r[0] != "Codeware"]
        assert len(loose_results) == 1

    def test_windows_backslash_paths(self):
        f = ModFile(
            filename="init.lua",
            file_path="mods\\AppearanceMenuMod\\init.lua",
            source_folder="mods",
        )
        result = group_mod_files([f])
        assert len(result) == 1
        assert result[0][0] == "Appearance Menu Mod"
        assert result[0][2] == 1.0

    def test_folder_name_cleaned_for_display(self):
        """Folder names like ##########VendorsXL should be cleaned for display."""
        files = [
            _file("data.json", folder="mods", subfolder="##########VendorsXL"),
        ]
        result = group_mod_files(files)
        assert result[0][0] == "Vendors XL"

    def test_deeply_nested_uses_first_component(self):
        """Deeply nested files use the first path component as the group name."""
        f = ModFile(
            filename="cache.json",
            file_path="mods/Codeware/storage/cache.json",
            source_folder="mods",
        )
        result = group_mod_files([f])
        assert len(result) == 1
        assert result[0][0] == "Codeware"

    def test_loose_files_still_clustered(self):
        """Files directly in source_folder should still go through clustering."""
        files = [
            _file("enhanced_weather_part1.archive", folder="archive/pc/mod"),
            _file("enhanced_weather_part2.archive", folder="archive/pc/mod"),
        ]
        result = group_mod_files(files)
        assert len(result) == 1
        _, grouped, _ = result[0]
        assert len(grouped) == 2

    def test_double_slash_path_treated_as_loose(self):
        """Double-slash in file_path should not produce empty folder name."""
        f = ModFile(
            filename="init.lua",
            file_path="mods//init.lua",
            source_folder="mods",
        )
        result = group_mod_files([f])
        assert len(result) == 1
        assert result[0][0] != ""

    def test_trailing_slash_on_source_folder(self):
        """Trailing slash on source_folder should not break folder extraction."""
        f = ModFile(
            filename="init.lua",
            file_path="mods/AppearanceMenuMod/init.lua",
            source_folder="mods/",
        )
        result = group_mod_files([f])
        assert len(result) == 1
        assert result[0][0] == "Appearance Menu Mod"
        assert result[0][2] == 1.0


class TestCrossFolderMerge:
    def test_cet_folder_and_loose_archive_merge(self):
        """CET folder ##EgghancedBloodFx + loose zEgghancedBloodFx.archive → 1 group."""
        cet = "bin/x64/plugins/cyber_engine_tweaks/mods"
        files = [
            _file("init.lua", folder=cet, subfolder="##EgghancedBloodFx"),
            _file("zEgghancedBloodFx.archive", folder="archive/pc/mod"),
        ]
        result = group_mod_files(files)
        assert len(result) == 1
        name, grouped, _conf = result[0]
        assert len(grouped) == 2
        assert "egghanced" in name.lower()

    def test_different_names_not_merged(self):
        """Groups with different normalized names stay separate."""
        files = [
            _file("init.lua", folder="mods", subfolder="ModAlpha"),
            _file("init.lua", folder="mods", subfolder="ModBeta"),
        ]
        result = group_mod_files(files)
        assert len(result) == 2

    def test_hash_and_z_prefix_variants_merge(self):
        """##ModName folder + zModName.archive → merged via identical normalized name."""
        files = [
            _file("config.json", folder="mods", subfolder="##ModName"),
            _file("zModName.archive", folder="archive/pc/mod"),
        ]
        result = group_mod_files(files)
        assert len(result) == 1
        assert len(result[0][1]) == 2
