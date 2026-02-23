from rippermod_manager.matching.normalization import (
    clean_display_name,
    split_camel,
    strip_ordering_prefix,
)


class TestSplitCamel:
    def test_basic_camel(self):
        assert split_camel("EgghancedBloodFx") == "Egghanced Blood Fx"

    def test_acronym_then_word(self):
        assert split_camel("CETMod") == "CET Mod"

    def test_consecutive_acronyms(self):
        assert split_camel("XMLParser") == "XML Parser"

    def test_all_caps_unchanged(self):
        assert split_camel("ALLCAPS") == "ALLCAPS"

    def test_all_lower_unchanged(self):
        assert split_camel("simplemod") == "simplemod"

    def test_empty(self):
        assert split_camel("") == ""

    def test_single_char(self):
        assert split_camel("A") == "A"

    def test_two_words(self):
        assert split_camel("ModName") == "Mod Name"

    def test_mixed_with_numbers(self):
        # Numbers don't create CamelCase boundaries
        assert split_camel("Mod2077Tweaks") == "Mod2077Tweaks"


class TestStripOrderingPrefix:
    def test_hash_prefix(self):
        assert strip_ordering_prefix("##Mod") == "Mod"

    def test_many_hashes(self):
        assert strip_ordering_prefix("##########VendorsXL") == "VendorsXL"

    def test_z_prefix_before_upper(self):
        assert strip_ordering_prefix("zModName") == "ModName"

    def test_z_before_lower_unchanged(self):
        assert strip_ordering_prefix("zebra") == "zebra"

    def test_no_prefix(self):
        assert strip_ordering_prefix("ModName") == "ModName"

    def test_empty(self):
        assert strip_ordering_prefix("") == ""

    def test_only_hashes(self):
        assert strip_ordering_prefix("###") == ""

    def test_z_only(self):
        # Just 'z' alone — no uppercase follows, so unchanged
        assert strip_ordering_prefix("z") == "z"

    def test_hash_and_z_combined(self):
        assert strip_ordering_prefix("##zMod") == "zMod"


class TestCleanDisplayName:
    def test_egghanced(self):
        assert clean_display_name("##EgghancedBloodFx") == "Egghanced Blood FX"

    def test_vendors_xl(self):
        assert clean_display_name("##########VendorsXL") == "Vendors XL"

    def test_cet_mod(self):
        assert clean_display_name("CETMod") == "CET Mod"

    def test_appearance_menu_mod(self):
        assert clean_display_name("AppearanceMenuMod") == "Appearance Menu Mod"

    def test_simple_name(self):
        assert clean_display_name("Codeware") == "Codeware"

    def test_underscored_name(self):
        assert clean_display_name("my_mod_name") == "My Mod Name"

    def test_empty(self):
        assert clean_display_name("") == ""

    def test_z_prefix_with_camel(self):
        assert clean_display_name("zEgghancedBloodFx") == "Egghanced Blood FX"

    def test_all_caps_acronym_preserved(self):
        result = clean_display_name("HDTextures")
        assert result == "HD Textures"

    def test_cyber_cat(self):
        assert clean_display_name("CyberCat") == "Cyber Cat"
