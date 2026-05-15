from rippermod_manager.services.vfs.naming import safe_dir_name, unique_staging_name


def test_safe_dir_name_replaces_unsafe_chars():
    assert safe_dir_name("My Cool Mod!") == "My_Cool_Mod"
    assert safe_dir_name("Phantom Liberty: HUD v2.1") == "Phantom_Liberty_HUD_v2.1"


def test_safe_dir_name_strips_underscores():
    assert safe_dir_name("___mod___") == "mod"
    assert safe_dir_name("!!!").endswith("mod")


def test_safe_dir_name_falls_back_for_empty_result():
    assert safe_dir_name("") == "mod"
    assert safe_dir_name("!!!") == "mod"


def test_unique_staging_name_returns_base_when_no_collision(tmp_path):
    assert unique_staging_name(tmp_path, "MyMod") == "MyMod"


def test_unique_staging_name_appends_suffix_on_collision(tmp_path):
    (tmp_path / "MyMod").mkdir()
    assert unique_staging_name(tmp_path, "MyMod") == "MyMod_2"

    (tmp_path / "MyMod_2").mkdir()
    assert unique_staging_name(tmp_path, "MyMod") == "MyMod_3"


def test_unique_staging_name_sanitises_first(tmp_path):
    """Different raw names that sanitise to the same staging dir collide correctly."""
    first = unique_staging_name(tmp_path, "My Cool Mod!")
    (tmp_path / first).mkdir()
    second = unique_staging_name(tmp_path, "My Cool Mod?")
    assert first == "My_Cool_Mod"
    assert second == "My_Cool_Mod_2"
