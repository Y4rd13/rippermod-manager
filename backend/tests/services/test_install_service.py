import os
import zipfile
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.install_service import (
    get_file_ownership_map,
    install_mod,
    list_available_archives,
    reparse_installed_mods,
    toggle_mod,
    uninstall_mod,
)


def _make_zip(path, files: dict[str, bytes]) -> None:
    """Create a zip archive with the given filename -> content mapping."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.fixture
def game_dir(tmp_path):
    """Return a temporary directory representing the game install directory."""
    d = tmp_path / "game"
    d.mkdir()
    return d


@pytest.fixture
def staging_dir(game_dir):
    """Return a staging (downloaded_mods) subdirectory inside the game dir."""
    staging = game_dir / "downloaded_mods"
    staging.mkdir()
    return staging


@pytest.fixture
def game(session, game_dir):
    """Create and persist a Game record pointing at game_dir."""
    g = Game(name="TestGame", domain_name="testgame", install_path=str(game_dir))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="mods"))
    session.commit()
    session.refresh(g)
    return g


class TestListAvailableArchives:
    def test_empty_when_no_staging_dir(self, session, game_dir):
        g = Game(name="G", domain_name="g", install_path=str(game_dir))
        session.add(g)
        session.commit()
        result = list_available_archives(g)
        assert result == []

    def test_returns_archives_in_staging(self, game, staging_dir):
        (staging_dir / "mod_a.zip").write_bytes(b"fake")
        (staging_dir / "mod_b.7z").write_bytes(b"fake")
        (staging_dir / "readme.txt").write_bytes(b"not an archive")

        result = list_available_archives(game)
        names = {p.name for p in result}
        assert "mod_a.zip" in names
        assert "mod_b.7z" in names
        assert "readme.txt" not in names

    def test_ignores_subdirectories(self, game, staging_dir):
        (staging_dir / "subdir").mkdir()
        result = list_available_archives(game)
        assert all(p.is_file() for p in result)


class TestGetFileOwnershipMap:
    def test_empty_when_no_mods(self, session, game):
        result = get_file_ownership_map(session, game.id)
        assert result == {}

    def test_maps_paths_to_mods(self, session, game):
        mod = InstalledMod(game_id=game.id, name="Alpha", source_archive="a.zip")
        session.add(mod)
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="mods/file.txt"))
        session.commit()

        result = get_file_ownership_map(session, game.id)
        assert "mods/file.txt" in result
        assert result["mods/file.txt"].name == "Alpha"

    def test_normalises_backslashes(self, session, game):
        mod = InstalledMod(game_id=game.id, name="Beta", source_archive="b.zip")
        session.add(mod)
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="mods\\win_path.txt"))
        session.commit()

        result = get_file_ownership_map(session, game.id)
        assert "mods/win_path.txt" in result

    def test_paths_are_lowercase(self, session, game):
        mod = InstalledMod(game_id=game.id, name="C", source_archive="c.zip")
        session.add(mod)
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="Mods/UPPER.TXT"))
        session.commit()

        result = get_file_ownership_map(session, game.id)
        assert "mods/upper.txt" in result


class TestInstallMod:
    def test_installs_files_and_creates_db_record(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "MyMod.zip"
        _make_zip(archive, {"mods/mymod.txt": b"content"})

        result = install_mod(game, archive, session)

        assert result.files_extracted == 1
        assert result.name == "MyMod"

        installed = session.exec(select(InstalledMod).where(InstalledMod.name == "MyMod")).first()
        assert installed is not None
        assert (game_dir / "mods" / "mymod.txt").exists()

    def test_installs_files_to_correct_paths(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "200-TestMod.zip"
        _make_zip(archive, {"a/b/c.txt": b"deep"})

        install_mod(game, archive, session)

        assert (game_dir / "a" / "b" / "c.txt").exists()

    def test_skips_directory_entries(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "DirMod.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.mkdir("subdir")
            zf.writestr("subdir/file.txt", b"hi")

        result = install_mod(game, archive, session)
        # Only the file should be counted, not the directory
        assert result.files_extracted == 1

    def test_duplicate_mod_raises_value_error(self, session, game, staging_dir):
        archive = staging_dir / "MyMod.zip"
        _make_zip(archive, {"a.txt": b"a"})

        install_mod(game, archive, session)

        with pytest.raises(ValueError, match="already installed"):
            install_mod(game, archive, session)

    def test_redmod_archive_extracts_under_mods_prefix(self, session, game_dir, staging_dir):
        """REDmod archives package as ``<modname>/info.json`` at the zip root.
        After install, the extracted files must live at
        ``<staging>/<safe_name>/mods/<modname>/...`` and the InstalledModFile
        records must use the ``mods/`` prefix so deploy creates junctions at
        ``<game>/mods/<modname>/`` where the engine looks.

        This is the full integration: detect_layout → apply_layout_transform →
        extraction → InstalledMod records → link_kind heuristic.  Without the
        REDMOD layout detection + `add_prefix`, files would land at the root and
        `link_kind` would default to `hardlink`, breaking REDmod loading.
        """
        # Cyberpunk domain so known_roots includes the real REDmod marker set
        cp_game = Game(
            name="CP77Test",
            domain_name="cyberpunk2077",
            install_path=str(game_dir),
        )
        session.add(cp_game)
        session.flush()
        session.add(GameModPath(game_id=cp_game.id, relative_path="mods"))
        session.commit()

        archive = staging_dir / "MyREDmod-12345-1-0.zip"
        _make_zip(
            archive,
            {
                "MyREDmodPkg/info.json": b'{"name":"MyREDmod","version":"1.0"}',
                "MyREDmodPkg/archives/test.archive": b"FAKE",
                "MyREDmodPkg/scripts/init.script": b"// noop\n",
            },
        )

        # auto_deploy=False so we don't try to create real junctions on the test FS
        # (the test machine may be Linux/macOS where mklink doesn't exist). The
        # important state is the staging layout and the InstalledModFile records.
        result = install_mod(cp_game, archive, session, auto_deploy=False)

        assert result.files_extracted == 3

        installed = session.exec(
            select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)
        ).one()
        files = sorted(f.relative_path for f in installed.files)

        # All three files MUST be prefixed with mods/<modname>/
        assert files == [
            "mods/MyREDmodPkg/archives/test.archive",
            "mods/MyREDmodPkg/info.json",
            "mods/MyREDmodPkg/scripts/init.script",
        ], f"REDmod files extracted without mods/ prefix — engine won't find them. Got: {files}"

        # link_kind must be junction for every record (mods/<x>/<more>/ matches
        # install_service's heuristic)
        kinds = {f.link_kind for f in installed.files}
        assert kinds == {"junction"}, f"Expected all junctions, got: {kinds}"

        # Staging layout: files live under <safe>/mods/<modname>/...
        safe = installed.staging_dir
        assert (staging_dir / safe / "mods" / "MyREDmodPkg" / "info.json").exists()
        assert (staging_dir / safe / "mods" / "MyREDmodPkg" / "archives" / "test.archive").exists()
        # And NOT at the wrong root path
        assert not (staging_dir / safe / "MyREDmodPkg" / "info.json").exists()

    def test_missing_archive_raises_file_not_found(self, session, game, tmp_path):
        missing = tmp_path / "nonexistent.zip"
        with pytest.raises(FileNotFoundError):
            install_mod(game, missing, session)

    def test_missing_game_dir_raises_file_not_found(self, session, tmp_path):
        g = Game(name="NoDir", domain_name="nodir", install_path=str(tmp_path / "missing"))
        session.add(g)
        session.commit()
        archive = tmp_path / "mod.zip"
        _make_zip(archive, {"x.txt": b"x"})
        with pytest.raises(FileNotFoundError):
            install_mod(g, archive, session)

    def test_skip_conflicts_skips_files(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "SkipMod.zip"
        _make_zip(archive, {"keep.txt": b"keep", "skip.txt": b"skip"})

        result = install_mod(game, archive, session, skip_conflicts=["skip.txt"])

        assert result.files_extracted == 1
        assert result.files_skipped == 1
        assert not (game_dir / "skip.txt").exists()
        assert (game_dir / "keep.txt").exists()

    def test_nexus_format_stores_metadata(self, session, game, staging_dir):
        archive = staging_dir / "CET-107-1-37-1-1759193708.zip"
        _make_zip(archive, {"cet.txt": b"cet"})

        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.nexus_mod_id == 107
        assert installed.upload_timestamp == 1759193708

    def test_file_ownership_each_mod_has_its_own_staging(
        self, session, game, game_dir, staging_dir
    ):
        # Install mod A — each mod gets an isolated staging dir
        archive_a = staging_dir / "ModA.zip"
        _make_zip(archive_a, {"shared.txt": b"from A"})
        result_a = install_mod(game, archive_a, session)

        # Mod A's staging copy must exist with its content
        staging_a = game_dir / "downloaded_mods" / result_a.installed_mod_name_safe
        assert (staging_a / "shared.txt").read_bytes() == b"from A"

        # Mod A is the DB owner of shared.txt
        ownership = get_file_ownership_map(session, game.id)
        assert ownership.get("shared.txt") is not None
        assert ownership["shared.txt"].name == "ModA"


class TestUninstallMod:
    def test_removes_files_and_db_record(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "ToRemove.zip"
        _make_zip(archive, {"mods/remove.txt": b"bye"})
        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files

        unresult = uninstall_mod(installed, game, session)

        assert unresult.files_deleted == 1
        assert not (game_dir / "mods" / "remove.txt").exists()
        assert session.get(InstalledMod, result.installed_mod_id) is None

    def test_removes_disabled_files(self, session, game, game_dir, staging_dir):
        # VFS model (Task 4.3): toggle_mod is DB-driven — disabling removes game-dir
        # hardlinks (no .disabled rename). Uninstall then removes staging + DB record.
        # Important invariants:
        # - files_deleted reflects the mod's registered file count (not disk success count)
        # - the DB record is gone
        # - the staging subtree is removed
        archive = staging_dir / "ToggleMod.zip"
        _make_zip(archive, {"mods/file.txt": b"data"})
        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_mod(installed, game, session)

        # Reload after toggle (disabled=True now)
        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files

        unresult = uninstall_mod(installed, game, session)
        # files_deleted == file_count registered in DB (1), regardless of disk state
        assert unresult.files_deleted == 1
        # DB record must be gone
        assert session.get(InstalledMod, result.installed_mod_id) is None
        # Staging subtree must be removed
        staging_path = game_dir / "downloaded_mods" / result.installed_mod_name_safe
        assert not staging_path.exists()

    def test_uninstall_with_profile_and_load_order_refs(self, session, game, game_dir, staging_dir):
        """Uninstalling a mod referenced by profile entries / load order prefs must not FK-crash."""
        from rippermod_manager.models.load_order import LoadOrderPreference
        from rippermod_manager.models.profile import Profile, ProfileEntry

        a1 = staging_dir / "ModA.zip"
        _make_zip(a1, {"mods/a.txt": b"a"})
        a2 = staging_dir / "ModB.zip"
        _make_zip(a2, {"mods/b.txt": b"b"})
        r1 = install_mod(game, a1, session)
        r2 = install_mod(game, a2, session)

        profile = Profile(game_id=game.id, name="test-profile")
        session.add(profile)
        session.flush()
        session.add(ProfileEntry(profile_id=profile.id, installed_mod_id=r1.installed_mod_id))
        session.add(
            LoadOrderPreference(
                game_id=game.id,
                winner_mod_id=r1.installed_mod_id,
                loser_mod_id=r2.installed_mod_id,
            )
        )
        session.commit()

        mod_a = session.get(InstalledMod, r1.installed_mod_id)
        session.refresh(mod_a)
        _ = mod_a.files

        uninstall_mod(mod_a, game, session)

        assert session.get(InstalledMod, r1.installed_mod_id) is None
        pe = session.exec(
            select(ProfileEntry).where(ProfileEntry.installed_mod_id == r1.installed_mod_id)
        ).first()
        assert pe is None
        lop = session.exec(
            select(LoadOrderPreference).where(
                LoadOrderPreference.winner_mod_id == r1.installed_mod_id
            )
        ).first()
        assert lop is None
        # ModB (loser side) must NOT be affected
        assert session.get(InstalledMod, r2.installed_mod_id) is not None

    def test_tolerates_already_missing_files(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "GoneMod.zip"
        _make_zip(archive, {"mods/gone.txt": b"gone"})
        result = install_mod(game, archive, session)

        # Manually remove the hardlink at the game-dir path — vfs_unlink is idempotent
        (game_dir / "mods" / "gone.txt").unlink()

        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        unresult = uninstall_mod(installed, game, session)
        # In the VFS model, files_deleted == registered file count (not disk success count).
        # vfs_unlink silently no-ops on missing dst, so uninstall always completes cleanly.
        assert unresult.files_deleted == 1
        assert session.get(InstalledMod, result.installed_mod_id) is None


class TestToggleMod:
    def test_disable_unlinks_game_dir_file(self, session, game, game_dir, staging_dir):
        # VFS model: disable removes the game-dir hardlink; no .disabled rename.
        archive = staging_dir / "ToggleMe.zip"
        _make_zip(archive, {"mods/mod.txt": b"data"})
        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_result = toggle_mod(installed, game, session)

        assert toggle_result.disabled is True
        assert toggle_result.files_affected == 1
        # Game-dir hardlink gone; no .disabled rename artifact.
        assert not (game_dir / "mods" / "mod.txt").exists()
        assert not (game_dir / "mods" / "mod.txt.disabled").exists()
        # Staging must still be intact.
        staging_file = (
            game_dir / "downloaded_mods" / result.installed_mod_name_safe / "mods" / "mod.txt"
        )
        assert staging_file.exists(), "staging file must survive disable"

    def test_enable_restores_files(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "ToggleBack.zip"
        _make_zip(archive, {"mods/back.txt": b"data"})
        result = install_mod(game, archive, session)

        # Disable first
        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_mod(installed, game, session)

        # Re-enable
        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_result = toggle_mod(installed, game, session)

        assert toggle_result.disabled is False
        # Game-dir hardlink re-created; no .disabled artifact.
        assert (game_dir / "mods" / "back.txt").exists()
        assert not (game_dir / "mods" / "back.txt.disabled").exists()

    def test_toggle_updates_disabled_field(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "StateCheck.zip"
        _make_zip(archive, {"mods/state.txt": b"x"})
        result = install_mod(game, archive, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.disabled is False
        session.refresh(installed)
        _ = installed.files
        toggle_mod(installed, game, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.disabled is True

    def test_toggle_twice_returns_to_enabled(self, session, game, game_dir, staging_dir):
        archive = staging_dir / "DoubleToggle.zip"
        _make_zip(archive, {"mods/double.txt": b"x"})
        result = install_mod(game, archive, session)

        for _ in range(2):
            installed = session.get(InstalledMod, result.installed_mod_id)
            session.refresh(installed)
            _ = installed.files
            toggle_mod(installed, game, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.disabled is False
        assert (game_dir / "mods" / "double.txt").exists()

    def test_toggle_enable_is_idempotent_on_already_linked_files(
        self, session, game, game_dir, staging_dir
    ):
        """Re-enabling a mod that's already (partially) linked must not raise.

        Mirrors the plan_deploy idempotency guard for the toggle re-enable
        path: if a file is already correctly hardlinked, the per-mod plan
        skips it instead of emitting an op that would fail with
        AlreadyExistsError.
        """
        archive = staging_dir / "IdempotentEnable.zip"
        _make_zip(archive, {"r6/scripts/idem.reds": b"// idem"})
        result = install_mod(game, archive, session)

        # Disable, then re-enable
        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_mod(installed, game, session)  # disable

        # Manually re-create the hardlink that the disable removed, simulating
        # a state where the file is already correctly linked when re-enable runs
        staging_file = (
            game_dir / "downloaded_mods" / installed.staging_dir / "r6" / "scripts" / "idem.reds"
        )
        game_file = game_dir / "r6" / "scripts" / "idem.reds"
        game_file.parent.mkdir(parents=True, exist_ok=True)
        os.link(staging_file, game_file)

        # Re-enable: must succeed without AlreadyExistsError; the plan should
        # be empty because the hardlink is already in place.
        installed = session.get(InstalledMod, result.installed_mod_id)
        session.refresh(installed)
        _ = installed.files
        toggle_mod(installed, game, session)

        installed = session.get(InstalledMod, result.installed_mod_id)
        assert installed.disabled is False
        assert game_file.exists()
        assert os.path.samefile(staging_file, game_file)


class TestReparseInstalledMods:
    def test_updates_stale_metadata(self, session, game):
        """Mods stored with an old parser get their metadata corrected."""
        mod = InstalledMod(
            game_id=game.id,
            name="Wrong Name-6968-v",
            source_archive="NC_Ambient_NPCs_v3LITE (Definitive Edition)-6968-v-3-0-1742148061.rar",
            nexus_mod_id=3,
            installed_version="0",
            upload_timestamp=None,
        )
        session.add(mod)
        session.commit()

        updated = reparse_installed_mods(game.id, session)

        assert updated == 1
        session.refresh(mod)
        assert mod.nexus_mod_id == 6968
        assert mod.installed_version == "v.3.0"
        assert mod.upload_timestamp == 1742148061
        assert "6968" not in mod.name or mod.name != "Wrong Name-6968-v"

    def test_no_changes_when_already_correct(self, session, game):
        """Mods that already match the parser output are not touched."""
        mod = InstalledMod(
            game_id=game.id,
            name="CET",
            source_archive="CET-107-1-37-1-1759193708.zip",
            nexus_mod_id=107,
            installed_version="1.37.1",
            upload_timestamp=1759193708,
        )
        session.add(mod)
        session.commit()

        updated = reparse_installed_mods(game.id, session)
        assert updated == 0

    def test_skips_mods_without_source_archive(self, session, game):
        """Mods with empty source_archive are excluded from reparsing."""
        mod = InstalledMod(
            game_id=game.id,
            name="Manual Mod",
            source_archive="",
        )
        session.add(mod)
        session.commit()

        updated = reparse_installed_mods(game.id, session)
        assert updated == 0

    def test_partial_update_only_changed_fields(self, session, game):
        """Only fields that differ from the parser are updated."""
        mod = InstalledMod(
            game_id=game.id,
            name="CET",
            source_archive="CET-107-1-37-1-1759193708.zip",
            nexus_mod_id=107,
            installed_version="0.0.0",  # wrong version only
            upload_timestamp=1759193708,
        )
        session.add(mod)
        session.commit()

        updated = reparse_installed_mods(game.id, session)
        assert updated == 1
        session.refresh(mod)
        assert mod.name == "CET"  # unchanged
        assert mod.nexus_mod_id == 107  # unchanged
        assert mod.installed_version == "1.37.1"  # fixed
        assert mod.upload_timestamp == 1759193708  # unchanged


@pytest.fixture
def tmp_game(tmp_path):
    """Return (game, session) backed by a fresh in-memory DB and a temp game dir."""
    import rippermod_manager.models  # noqa: F401 — register all tables

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    game_dir = tmp_path / "cp2077"
    game_dir.mkdir()
    (game_dir / "downloaded_mods").mkdir()

    with Session(engine) as sess:
        g = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(game_dir))
        sess.add(g)
        sess.flush()
        sess.add(GameModPath(game_id=g.id, relative_path="mods"))
        sess.commit()
        sess.refresh(g)
        yield g, sess


@pytest.fixture
def sample_archive(tmp_path):
    """A zip archive with a single r6/scripts/foo.reds file."""
    archive = tmp_path / "SampleMod-v1.zip"
    _make_zip(archive, {"r6/scripts/foo.reds": b"// sample"})
    return archive


class TestVfsHardlinks:
    """Verify that install_mod uses staging + hardlinks rather than direct game-dir writes."""

    def test_install_mod_writes_to_staging_with_hardlinks(
        self, session, game, game_dir, staging_dir
    ):
        """Files live in staging and are hardlinked into game-dir paths after install."""
        from pathlib import Path

        archive = staging_dir / "SampleMod-v1.zip"
        _make_zip(archive, {"r6/scripts/foo.reds": b"// sample"})

        result = install_mod(game, archive, session)

        assert result.installed_mod_name_safe != "", "installed_mod_name_safe must be populated"

        staging = game_dir / "downloaded_mods" / result.installed_mod_name_safe
        assert staging.exists(), f"staging dir {staging} missing"
        assert any(staging.rglob("*")), "no files in staging"

        installed = session.exec(
            select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)
        ).one()
        assert installed.staging_dir == result.installed_mod_name_safe
        assert installed.deployed is True

        _ = installed.files
        for f in installed.files:
            src = staging / f.source_path.replace("\\", "/")
            dst = Path(game.install_path) / f.relative_path.replace("\\", "/")
            assert src.exists(), f"staging file {src} missing"
            assert dst.exists(), f"game-dir hardlink {dst} missing"
            assert os.path.samefile(src, dst), f"{src} and {dst} are not the same inode"
            assert f.source_path == f.relative_path, (
                "source_path should mirror relative_path for VFS installs"
            )
            assert f.link_kind == "hardlink", f"expected hardlink, got {f.link_kind!r}"

    def test_install_mod_name_safe_returned_in_result(self, session, game, game_dir, staging_dir):
        """InstallResult.installed_mod_name_safe is the sanitised staging directory name."""
        archive = staging_dir / "My_Awesome_Mod.zip"
        _make_zip(archive, {"r6/scripts/x.reds": b"x"})

        result = install_mod(game, archive, session)

        assert result.installed_mod_name_safe != ""
        staging = game_dir / "downloaded_mods" / result.installed_mod_name_safe
        assert staging.is_dir(), "staging dir created with sanitised name"

    def test_uninstall_removes_hardlinks_and_staging(self, session, game, game_dir, staging_dir):
        """Uninstall removes game-dir hardlinks AND the staging subtree."""
        from pathlib import Path

        archive = staging_dir / "SampleMod-v1.zip"
        _make_zip(archive, {"r6/scripts/foo.reds": b"// sample"})

        result = install_mod(game, archive, session)
        installed = session.exec(
            select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)
        ).one()

        game_path = Path(game.install_path) / "r6" / "scripts" / "foo.reds"
        staging_path = (
            Path(game.install_path)
            / "downloaded_mods"
            / result.installed_mod_name_safe
            / "r6"
            / "scripts"
            / "foo.reds"
        )
        assert game_path.exists(), "game-dir hardlink must exist after install"
        assert staging_path.exists(), "staging file must exist after install"

        uninstall_mod(installed, game, session)

        assert not game_path.exists(), "game-dir hardlink should be gone after uninstall"
        staging_dir_path = (
            Path(game.install_path) / "downloaded_mods" / result.installed_mod_name_safe
        )
        assert not staging_dir_path.exists(), "staging dir should be removed after uninstall"
        assert (
            session.exec(
                select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)
            ).first()
            is None
        ), "InstalledMod DB record should be deleted"

    def test_toggle_disable_unlinks_keeps_staging(self, tmp_game, sample_archive):
        """Disabling unlinks game-dir hardlinks but keeps staging intact."""
        game, session = tmp_game
        result = install_mod(game, sample_archive, session)
        installed = session.exec(
            select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)
        ).one()

        game_path = Path(game.install_path) / "r6" / "scripts" / "foo.reds"
        staging_path = (
            Path(game.install_path)
            / "downloaded_mods"
            / result.installed_mod_name_safe
            / "r6"
            / "scripts"
            / "foo.reds"
        )
        assert game_path.exists()
        assert staging_path.exists()

        toggle_mod(installed, game, session)

        session.refresh(installed)
        assert installed.disabled is True
        assert not game_path.exists(), "game-dir hardlink should be gone after disable"
        assert staging_path.exists(), "staging file should survive disable"

    def test_toggle_re_enable_recreates_hardlink(self, tmp_game, sample_archive):
        """Re-enabling re-creates the game-dir hardlink from staging."""
        game, session = tmp_game
        result = install_mod(game, sample_archive, session)
        installed = session.exec(
            select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)
        ).one()

        game_path = Path(game.install_path) / "r6" / "scripts" / "foo.reds"
        staging_path = (
            Path(game.install_path)
            / "downloaded_mods"
            / result.installed_mod_name_safe
            / "r6"
            / "scripts"
            / "foo.reds"
        )

        toggle_mod(installed, game, session)  # disable
        session.refresh(installed)
        assert installed.disabled is True

        toggle_mod(installed, game, session)  # re-enable
        session.refresh(installed)
        assert installed.disabled is False
        assert game_path.exists()
        assert os.path.samefile(staging_path, game_path), (
            "re-enabled file must be a hardlink to staging"
        )

    def test_uninstall_triggers_save_backup(self, tmp_game, sample_archive, monkeypatch):
        """uninstall_mod takes a pre-uninstall save snapshot before removing files."""
        game, session = tmp_game
        result = install_mod(game, sample_archive, session)
        installed = session.exec(
            select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)
        ).one()

        from rippermod_manager.services import save_backup_service

        calls: list[str] = []
        monkeypatch.setattr(
            save_backup_service, "maybe_backup_before", lambda g, s, *, reason: calls.append(reason)
        )
        uninstall_mod(installed, game, session)
        assert calls == ["pre-uninstall"]

    def test_disable_triggers_backup_enable_does_not(self, tmp_game, sample_archive, monkeypatch):
        """Disabling snapshots saves; re-enabling does not."""
        game, session = tmp_game
        result = install_mod(game, sample_archive, session)
        installed = session.exec(
            select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)
        ).one()

        from rippermod_manager.services import save_backup_service

        calls: list[str] = []
        monkeypatch.setattr(
            save_backup_service, "maybe_backup_before", lambda g, s, *, reason: calls.append(reason)
        )
        toggle_mod(installed, game, session)  # disable → backup
        toggle_mod(installed, game, session)  # re-enable → no backup
        assert calls == ["pre-disable"]
