from pathlib import Path

from chat_nexus_mod_manager.scanner.service import compute_hash, scan_game_mods


class TestComputeHash:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        assert compute_hash(f) == compute_hash(f)

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("identical")
        f2.write_text("identical")
        assert compute_hash(f1) == compute_hash(f2)

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("alpha")
        f2.write_text("beta")
        assert compute_hash(f1) != compute_hash(f2)


class TestScanGameMods:
    def test_nonexistent_path(self, session, make_game):
        game = make_game(install_path="/nonexistent/path")
        result = scan_game_mods(game, session)
        assert result.files_found == 0
        assert result.groups_created == 0
        assert result.new_files == 0

    def test_empty_dir(self, tmp_path, session, make_game):
        mod_dir = tmp_path / "archive" / "pc" / "mod"
        mod_dir.mkdir(parents=True)
        game = make_game(
            install_path=str(tmp_path),
            mod_paths=["archive/pc/mod"],
        )
        result = scan_game_mods(game, session)
        assert result.files_found == 0

    def test_discovers_archive(self, tmp_path, session, make_game):
        mod_dir = tmp_path / "archive" / "pc" / "mod"
        mod_dir.mkdir(parents=True)
        (mod_dir / "cool_mod.archive").write_text("data")
        game = make_game(
            install_path=str(tmp_path),
            mod_paths=["archive/pc/mod"],
        )
        result = scan_game_mods(game, session)
        assert result.files_found == 1
        assert result.new_files == 1
        assert result.groups_created == 1

    def test_skips_bad_extension(self, tmp_path, session, make_game):
        mod_dir = tmp_path / "archive" / "pc" / "mod"
        mod_dir.mkdir(parents=True)
        (mod_dir / "readme.txt").write_text("nothing")
        game = make_game(
            install_path=str(tmp_path),
            mod_paths=["archive/pc/mod"],
        )
        result = scan_game_mods(game, session)
        assert result.files_found == 0

    def test_skips_pycache(self, tmp_path, session, make_game):
        mod_dir = tmp_path / "archive" / "pc" / "mod" / "__pycache__"
        mod_dir.mkdir(parents=True)
        (mod_dir / "cached.archive").write_text("data")
        game = make_game(
            install_path=str(tmp_path),
            mod_paths=["archive/pc/mod"],
        )
        result = scan_game_mods(game, session)
        assert result.files_found == 0

    def test_existing_file_not_double_counted(self, tmp_path, session, make_game):
        mod_dir = tmp_path / "archive" / "pc" / "mod"
        mod_dir.mkdir(parents=True)
        (mod_dir / "mod.archive").write_text("data")
        game = make_game(
            install_path=str(tmp_path),
            mod_paths=["archive/pc/mod"],
        )
        scan_game_mods(game, session)
        result2 = scan_game_mods(game, session)
        assert result2.new_files == 0
        assert result2.files_found == 1

    def test_creates_mod_group(self, tmp_path, session, make_game):
        mod_dir = tmp_path / "archive" / "pc" / "mod"
        mod_dir.mkdir(parents=True)
        (mod_dir / "weather_enhanced.archive").write_text("data1")
        game = make_game(
            install_path=str(tmp_path),
            mod_paths=["archive/pc/mod"],
        )
        result = scan_game_mods(game, session)
        assert result.groups_created >= 1
