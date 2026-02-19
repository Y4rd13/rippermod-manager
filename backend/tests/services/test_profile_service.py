import zipfile
from datetime import UTC, datetime

import pytest
from sqlmodel import select

from chat_nexus_mod_manager.models.game import Game, GameModPath
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.profile import Profile
from chat_nexus_mod_manager.schemas.profile import ProfileCreate, ProfileExport, ProfileExportMod
from chat_nexus_mod_manager.services.install_service import install_mod
from chat_nexus_mod_manager.services.profile_service import (
    create_profile,
    delete_profile,
    export_profile,
    import_profile,
    list_profiles,
    load_profile,
)


def _make_zip(path, files: dict[str, bytes]) -> None:
    """Create a zip archive with the given filename -> content mapping."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.fixture
def game_and_dirs(session, tmp_path):
    """Yield a (game, game_dir, staging_dir) tuple with filesystem dirs set up."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    staging = game_dir / "downloaded_mods"
    staging.mkdir()

    g = Game(name="ProfileGame", domain_name="pg", install_path=str(game_dir))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="mods"))
    session.commit()
    session.refresh(g)
    return g, game_dir, staging


class TestListProfiles:
    def test_empty_when_no_profiles(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        result = list_profiles(game, session)
        assert result == []

    def test_returns_created_profiles(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        create_profile(game, ProfileCreate(name="Alpha"), session)
        create_profile(game, ProfileCreate(name="Beta"), session)

        result = list_profiles(game, session)
        names = {p.name for p in result}
        assert "Alpha" in names
        assert "Beta" in names

    def test_profiles_include_mod_count(self, session, game_and_dirs):
        game, _game_dir, staging = game_and_dirs
        archive = staging / "Mod1.zip"
        _make_zip(archive, {"mods/mod1.txt": b"m1"})
        install_mod(game, archive, session)

        create_profile(game, ProfileCreate(name="WithMod"), session)

        result = list_profiles(game, session)
        assert len(result) == 1
        assert result[0].mod_count == 1


class TestCreateProfile:
    def test_creates_profile(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="MyProfile"), session)

        assert out.name == "MyProfile"
        assert out.game_id == game.id
        assert isinstance(out.id, int)

    def test_profile_captures_installed_mods(self, session, game_and_dirs):
        game, _game_dir, staging = game_and_dirs
        archive_a = staging / "ModA.zip"
        archive_b = staging / "ModB.zip"
        _make_zip(archive_a, {"mods/a.txt": b"a"})
        _make_zip(archive_b, {"mods/b.txt": b"b"})
        install_mod(game, archive_a, session)
        install_mod(game, archive_b, session)

        out = create_profile(game, ProfileCreate(name="TwoMods"), session)

        assert out.mod_count == 2
        mod_names = {m.name for m in out.mods}
        assert "ModA" in mod_names
        assert "ModB" in mod_names

    def test_duplicate_name_replaces_existing(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        create_profile(game, ProfileCreate(name="Dupe"), session)
        out2 = create_profile(game, ProfileCreate(name="Dupe"), session)

        profiles = list_profiles(game, session)
        assert len(profiles) == 1
        assert profiles[0].id == out2.id

    def test_profile_stores_disabled_state(self, session, game_and_dirs):
        game, _game_dir, staging = game_and_dirs
        archive = staging / "Toggled.zip"
        _make_zip(archive, {"mods/t.txt": b"t"})
        install_mod(game, archive, session)

        # Manually mark the mod as disabled
        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "Toggled")).first()
        mod.disabled = True
        session.add(mod)
        session.commit()

        out = create_profile(game, ProfileCreate(name="WithDisabled"), session)

        assert out.mod_count == 1
        assert out.mods[0].enabled is False


class TestDeleteProfile:
    def test_delete_removes_profile(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        create_profile(game, ProfileCreate(name="ToDelete"), session)

        profile = session.exec(select(Profile).where(Profile.name == "ToDelete")).first()
        delete_profile(profile, session)

        assert session.get(Profile, profile.id) is None

    def test_empty_list_after_delete(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        create_profile(game, ProfileCreate(name="Gone"), session)
        profile = session.exec(select(Profile).where(Profile.name == "Gone")).first()
        delete_profile(profile, session)

        assert list_profiles(game, session) == []


class TestLoadProfile:
    def test_load_enables_disabled_mod(self, session, game_and_dirs):
        game, game_dir, staging = game_and_dirs
        archive = staging / "ReEnable.zip"
        _make_zip(archive, {"mods/re.txt": b"data"})
        install_mod(game, archive, session)

        # Create profile while mod is enabled
        profile_out = create_profile(game, ProfileCreate(name="EnabledState"), session)

        # Manually disable the mod
        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "ReEnable")).first()
        mod.disabled = True
        (game_dir / "mods" / "re.txt").rename(game_dir / "mods" / "re.txt.disabled")
        session.add(mod)
        session.commit()

        # Load the profile — mod should be re-enabled
        profile = session.get(Profile, profile_out.id)
        load_profile(profile, game, session)

        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "ReEnable")).first()
        assert mod.disabled is False

    def test_load_returns_profile_out(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        profile_out = create_profile(game, ProfileCreate(name="LoadMe"), session)
        profile = session.get(Profile, profile_out.id)

        result = load_profile(profile, game, session)

        assert result.name == "LoadMe"
        assert result.game_id == game.id


class TestExportProfile:
    def test_export_returns_profile_export(self, session, game_and_dirs):
        game, _game_dir, staging = game_and_dirs
        archive = staging / "ExportMod.zip"
        _make_zip(archive, {"mods/em.txt": b"em"})
        install_mod(game, archive, session)

        profile_out = create_profile(game, ProfileCreate(name="ExportMe"), session)
        profile = session.get(Profile, profile_out.id)

        result = export_profile(profile, game, session)

        assert result.profile_name == "ExportMe"
        assert result.game_name == game.name
        assert result.mod_count == 1
        assert result.mods[0].name == "ExportMod"

    def test_export_includes_nexus_id(self, session, game_and_dirs):
        game, _game_dir, staging = game_and_dirs
        archive = staging / "CET-107-1-37-1-1759193708.zip"
        _make_zip(archive, {"mods/cet.txt": b"cet"})
        install_mod(game, archive, session)

        profile_out = create_profile(game, ProfileCreate(name="WithNexus"), session)
        profile = session.get(Profile, profile_out.id)

        result = export_profile(profile, game, session)
        assert result.mods[0].nexus_mod_id == 107

    def test_export_has_exported_at_timestamp(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        profile_out = create_profile(game, ProfileCreate(name="Timestamp"), session)
        profile = session.get(Profile, profile_out.id)

        result = export_profile(profile, game, session)

        assert isinstance(result.exported_at, datetime)


class TestImportProfile:
    def test_import_matches_installed_mod_by_name(self, session, game_and_dirs):
        game, _game_dir, staging = game_and_dirs
        archive = staging / "ImportMod.zip"
        _make_zip(archive, {"mods/im.txt": b"im"})
        install_mod(game, archive, session)

        export_data = ProfileExport(
            profile_name="Imported",
            game_name=game.name,
            exported_at=datetime.now(UTC),
            mod_count=1,
            mods=[ProfileExportMod(name="ImportMod")],
        )

        result = import_profile(game, export_data, session)

        assert result.name == "Imported"
        assert result.mod_count == 1
        assert result.mods[0].name == "ImportMod"

    def test_import_matches_by_nexus_id(self, session, game_and_dirs):
        game, _game_dir, staging = game_and_dirs
        archive = staging / "CET-107-1-37-1-1759193708.zip"
        _make_zip(archive, {"mods/cet.txt": b"cet"})
        install_mod(game, archive, session)

        export_data = ProfileExport(
            profile_name="ByNexusId",
            game_name=game.name,
            exported_at=datetime.now(UTC),
            mod_count=1,
            mods=[ProfileExportMod(name="WrongName", nexus_mod_id=107)],
        )

        result = import_profile(game, export_data, session)
        # Matched via nexus_mod_id fallback
        assert result.mod_count == 1

    def test_import_skips_unmatched_mods(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        export_data = ProfileExport(
            profile_name="NoMatch",
            game_name=game.name,
            exported_at=datetime.now(UTC),
            mod_count=1,
            mods=[ProfileExportMod(name="DoesNotExist")],
        )

        result = import_profile(game, export_data, session)
        assert result.mod_count == 0

    def test_import_replaces_existing_profile_with_same_name(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        create_profile(game, ProfileCreate(name="Existing"), session)

        export_data = ProfileExport(
            profile_name="Existing",
            game_name=game.name,
            exported_at=datetime.now(UTC),
            mod_count=0,
            mods=[],
        )
        import_profile(game, export_data, session)

        profiles = list_profiles(game, session)
        assert len(profiles) == 1
        assert profiles[0].name == "Existing"
