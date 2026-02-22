import zipfile
from datetime import UTC, datetime

import pytest
from sqlmodel import select

from chat_nexus_mod_manager.models.game import Game, GameModPath
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.profile import Profile
from chat_nexus_mod_manager.schemas.profile import (
    ProfileCreate,
    ProfileExport,
    ProfileExportMod,
    ProfileUpdate,
)
from chat_nexus_mod_manager.services.install_service import install_mod
from chat_nexus_mod_manager.services.profile_service import (
    compare_profiles,
    create_profile,
    delete_profile,
    duplicate_profile,
    export_profile,
    import_profile,
    list_profiles,
    load_profile,
    preview_profile,
    update_profile,
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

    def test_creates_profile_with_description(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="Described", description="My notes"), session)
        assert out.description == "My notes"

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
        delete_profile(profile, game, session)

        assert session.get(Profile, profile.id) is None

    def test_empty_list_after_delete(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        create_profile(game, ProfileCreate(name="Gone"), session)
        profile = session.exec(select(Profile).where(Profile.name == "Gone")).first()
        delete_profile(profile, game, session)

        assert list_profiles(game, session) == []

    def test_delete_active_profile_clears_active(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="Active"), session)
        profile = session.get(Profile, out.id)
        load_profile(profile, game, session)
        session.refresh(game)
        assert game.active_profile_id == out.id

        delete_profile(profile, game, session)
        session.refresh(game)
        assert game.active_profile_id is None


class TestLoadProfile:
    def test_load_enables_disabled_mod(self, session, game_and_dirs):
        game, game_dir, staging = game_and_dirs
        archive = staging / "ReEnable.zip"
        _make_zip(archive, {"mods/re.txt": b"data"})
        install_mod(game, archive, session)

        profile_out = create_profile(game, ProfileCreate(name="EnabledState"), session)

        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "ReEnable")).first()
        mod.disabled = True
        (game_dir / "mods" / "re.txt").rename(game_dir / "mods" / "re.txt.disabled")
        session.add(mod)
        session.commit()

        profile = session.get(Profile, profile_out.id)
        load_profile(profile, game, session)

        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "ReEnable")).first()
        assert mod.disabled is False

    def test_load_returns_profile_load_result(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        profile_out = create_profile(game, ProfileCreate(name="LoadMe"), session)
        profile = session.get(Profile, profile_out.id)

        result = load_profile(profile, game, session)

        assert result.profile.name == "LoadMe"
        assert result.profile.game_id == game.id
        assert result.skipped_count == 0

    def test_load_sets_active_profile(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="ToLoad"), session)
        profile = session.get(Profile, out.id)
        load_profile(profile, game, session)

        session.refresh(game)
        assert game.active_profile_id == out.id

    def test_load_sets_last_loaded_at(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="Timestamped"), session)
        profile = session.get(Profile, out.id)
        result = load_profile(profile, game, session)

        assert result.profile.last_loaded_at is not None

    def test_load_reports_skipped_mods(self, session, game_and_dirs):
        game, _game_dir, staging = game_and_dirs
        archive = staging / "WillVanish.zip"
        _make_zip(archive, {"mods/v.txt": b"v"})
        install_mod(game, archive, session)

        out = create_profile(game, ProfileCreate(name="WithVanishing"), session)

        # Delete the installed mod to simulate it being uninstalled
        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "WillVanish")).first()
        session.delete(mod)
        session.commit()

        profile = session.get(Profile, out.id)
        result = load_profile(profile, game, session)
        assert result.skipped_count == 1
        assert result.skipped_mods[0].installed_mod_id is not None


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

        assert result.profile.name == "Imported"
        assert result.profile.mod_count == 1
        assert result.matched_count == 1

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
        assert result.matched_count == 1

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
        assert result.profile.mod_count == 0
        assert result.skipped_count == 1
        assert result.skipped_mods[0].name == "DoesNotExist"

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


class TestPreviewProfile:
    def test_preview_shows_enable_action(self, session, game_and_dirs):
        game, game_dir, staging = game_and_dirs
        archive = staging / "PreviewMod.zip"
        _make_zip(archive, {"mods/pm.txt": b"pm"})
        install_mod(game, archive, session)

        out = create_profile(game, ProfileCreate(name="Preview"), session)

        # Disable the mod
        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "PreviewMod")).first()
        mod.disabled = True
        (game_dir / "mods" / "pm.txt").rename(game_dir / "mods" / "pm.txt.disabled")
        session.add(mod)
        session.commit()

        profile = session.get(Profile, out.id)
        diff = preview_profile(profile, game, session)
        assert diff.enable_count == 1
        enable_entries = [e for e in diff.entries if e.action == "enable"]
        assert len(enable_entries) == 1
        assert enable_entries[0].mod_name == "PreviewMod"

    def test_preview_shows_unchanged(self, session, game_and_dirs):
        game, _, staging = game_and_dirs
        archive = staging / "UnchangedMod.zip"
        _make_zip(archive, {"mods/uc.txt": b"uc"})
        install_mod(game, archive, session)

        out = create_profile(game, ProfileCreate(name="Unchanged"), session)
        profile = session.get(Profile, out.id)

        diff = preview_profile(profile, game, session)
        assert diff.unchanged_count == 1
        assert diff.enable_count == 0
        assert diff.disable_count == 0

    def test_preview_shows_missing(self, session, game_and_dirs):
        game, _, staging = game_and_dirs
        archive = staging / "GoneMod.zip"
        _make_zip(archive, {"mods/gm.txt": b"gm"})
        install_mod(game, archive, session)

        out = create_profile(game, ProfileCreate(name="WithGone"), session)

        # Remove the installed mod
        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "GoneMod")).first()
        session.delete(mod)
        session.commit()

        profile = session.get(Profile, out.id)
        diff = preview_profile(profile, game, session)
        assert diff.missing_count == 1

    def test_preview_correct_counts(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="Empty"), session)
        profile = session.get(Profile, out.id)
        diff = preview_profile(profile, game, session)
        assert diff.enable_count == 0
        assert diff.disable_count == 0
        assert diff.missing_count == 0
        assert diff.unchanged_count == 0


class TestUpdateProfile:
    def test_rename_profile(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="Original"), session)
        profile = session.get(Profile, out.id)
        result = update_profile(profile, ProfileUpdate(name="Renamed"), game, session)
        assert result.name == "Renamed"

    def test_update_description(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="Desc"), session)
        profile = session.get(Profile, out.id)
        result = update_profile(
            profile, ProfileUpdate(description="New description"), game, session
        )
        assert result.description == "New description"

    def test_duplicate_name_raises_409(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        create_profile(game, ProfileCreate(name="TakenName"), session)
        out = create_profile(game, ProfileCreate(name="Other"), session)
        profile = session.get(Profile, out.id)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            update_profile(profile, ProfileUpdate(name="TakenName"), game, session)
        assert exc_info.value.status_code == 409


class TestDuplicateProfile:
    def test_duplicate_creates_copy(self, session, game_and_dirs):
        game, _, staging = game_and_dirs
        archive = staging / "DupeMod.zip"
        _make_zip(archive, {"mods/dm.txt": b"dm"})
        install_mod(game, archive, session)

        out = create_profile(game, ProfileCreate(name="Source"), session)
        source = session.get(Profile, out.id)
        result = duplicate_profile(source, "Copy", game, session)

        assert result.name == "Copy"
        assert result.mod_count == out.mod_count

    def test_duplicate_name_raises_409(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        create_profile(game, ProfileCreate(name="Existing"), session)
        out = create_profile(game, ProfileCreate(name="Source2"), session)
        source = session.get(Profile, out.id)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            duplicate_profile(source, "Existing", game, session)
        assert exc_info.value.status_code == 409

    def test_duplicate_copies_description(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="WithDesc", description="Notes"), session)
        source = session.get(Profile, out.id)
        result = duplicate_profile(source, "CloneDesc", game, session)
        assert result.description == "Notes"


class TestCompareProfiles:
    def test_compare_identical_profiles(self, session, game_and_dirs):
        game, _, staging = game_and_dirs
        archive = staging / "Same.zip"
        _make_zip(archive, {"mods/s.txt": b"s"})
        install_mod(game, archive, session)

        out_a = create_profile(game, ProfileCreate(name="A"), session)
        out_b = create_profile(game, ProfileCreate(name="B"), session)
        a = session.get(Profile, out_a.id)
        b = session.get(Profile, out_b.id)

        result = compare_profiles(a, b, game, session)
        assert result.in_both_count == 1
        assert result.only_in_a_count == 0
        assert result.only_in_b_count == 0

    def test_compare_disjoint_profiles(self, session, game_and_dirs):
        game, _, staging = game_and_dirs
        # Install both mods
        archive_a = staging / "OnlyA.zip"
        archive_b = staging / "OnlyB.zip"
        _make_zip(archive_a, {"mods/a.txt": b"a"})
        _make_zip(archive_b, {"mods/b.txt": b"b"})
        install_mod(game, archive_a, session)
        install_mod(game, archive_b, session)

        # Create ProfileA with only ModA (disable ModB first)
        mod_b = session.exec(select(InstalledMod).where(InstalledMod.name == "OnlyB")).first()
        mod_b.disabled = True
        session.add(mod_b)
        session.commit()
        out_a = create_profile(game, ProfileCreate(name="ProfileA"), session)

        # Create ProfileB with only ModB (flip states)
        mod_a = session.exec(select(InstalledMod).where(InstalledMod.name == "OnlyA")).first()
        mod_a.disabled = True
        mod_b.disabled = False
        session.add(mod_a)
        session.add(mod_b)
        session.commit()
        out_b = create_profile(game, ProfileCreate(name="ProfileB"), session)

        a = session.get(Profile, out_a.id)
        b = session.get(Profile, out_b.id)
        result = compare_profiles(a, b, game, session)
        # Both profiles contain both mods (just with different enabled states)
        assert result.in_both_count == 2
        # The enabled states differ for both mods
        differing = [e for e in result.in_both if e.enabled_in_a != e.enabled_in_b]
        assert len(differing) == 2


class TestActiveProfileAndDrift:
    def test_active_profile_indicator(self, session, game_and_dirs):
        game, _, _ = game_and_dirs
        out = create_profile(game, ProfileCreate(name="Active"), session)
        profile = session.get(Profile, out.id)
        load_profile(profile, game, session)

        profiles = list_profiles(game, session)
        active = [p for p in profiles if p.is_active]
        assert len(active) == 1
        assert active[0].name == "Active"

    def test_drift_detected_after_mod_toggle(self, session, game_and_dirs):
        game, game_dir, staging = game_and_dirs
        archive = staging / "DriftMod.zip"
        _make_zip(archive, {"mods/d.txt": b"d"})
        install_mod(game, archive, session)

        out = create_profile(game, ProfileCreate(name="DriftTest"), session)
        profile = session.get(Profile, out.id)
        load_profile(profile, game, session)

        # Toggle the mod
        mod = session.exec(select(InstalledMod).where(InstalledMod.name == "DriftMod")).first()
        mod.disabled = True
        (game_dir / "mods" / "d.txt").rename(game_dir / "mods" / "d.txt.disabled")
        session.add(mod)
        session.commit()

        profiles = list_profiles(game, session)
        active = [p for p in profiles if p.is_active]
        assert len(active) == 1
        assert active[0].is_drifted is True

    def test_no_drift_when_matching(self, session, game_and_dirs):
        game, _, staging = game_and_dirs
        archive = staging / "NoDrift.zip"
        _make_zip(archive, {"mods/nd.txt": b"nd"})
        install_mod(game, archive, session)

        out = create_profile(game, ProfileCreate(name="NoDriftTest"), session)
        profile = session.get(Profile, out.id)
        load_profile(profile, game, session)

        profiles = list_profiles(game, session)
        active = [p for p in profiles if p.is_active]
        assert len(active) == 1
        assert active[0].is_drifted is False
