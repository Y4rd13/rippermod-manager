"""Profile management: save, load, export, and import mod configurations.

A profile captures which installed mods are enabled for a specific game.
Profiles can be exported to a portable JSON format for sharing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.profile import Profile, ProfileEntry
from chat_nexus_mod_manager.schemas.profile import (
    ProfileCompareEntry,
    ProfileCompareOut,
    ProfileCreate,
    ProfileDiffEntry,
    ProfileDiffOut,
    ProfileExport,
    ProfileExportMod,
    ProfileImportResult,
    ProfileLoadResult,
    ProfileModOut,
    ProfileOut,
    ProfileUpdate,
    SkippedMod,
)
from chat_nexus_mod_manager.services.install_service import toggle_mod


def _check_drift(profile: Profile, game: Game, session: Session) -> bool:
    """Check if installed mod states have drifted from the profile snapshot."""
    _ = profile.entries
    profile_state: dict[int, bool] = {}
    for entry in profile.entries:
        profile_state[entry.installed_mod_id] = entry.enabled

    installed = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()

    installed_ids = {m.id for m in installed}
    profile_ids = set(profile_state.keys())

    if installed_ids != profile_ids:
        return True

    for mod in installed:
        expected_enabled = profile_state.get(mod.id)  # type: ignore[arg-type]
        if expected_enabled is None:
            return True
        actual_enabled = not mod.disabled
        if expected_enabled != actual_enabled:
            return True

    return False


def profile_to_out(profile: Profile, game: Game, session: Session) -> ProfileOut:
    """Convert a Profile model to a ProfileOut schema."""
    _ = profile.entries
    mod_ids = [e.installed_mod_id for e in profile.entries]
    installed_mods = (
        session.exec(select(InstalledMod).where(InstalledMod.id.in_(mod_ids))).all()
        if mod_ids
        else []
    )
    installed_map = {m.id: m for m in installed_mods}

    mods: list[ProfileModOut] = []
    for entry in profile.entries:
        installed = installed_map.get(entry.installed_mod_id)
        if installed:
            mods.append(
                ProfileModOut(
                    installed_mod_id=entry.installed_mod_id,
                    name=installed.name,
                    enabled=entry.enabled,
                )
            )

    is_active = game.active_profile_id == profile.id
    is_drifted = _check_drift(profile, game, session) if is_active else False

    return ProfileOut(
        id=profile.id,  # type: ignore[arg-type]
        name=profile.name,
        game_id=profile.game_id,
        description=profile.description,
        created_at=profile.created_at,
        last_loaded_at=profile.last_loaded_at,
        is_active=is_active,
        is_drifted=is_drifted,
        mod_count=len(mods),
        mods=mods,
    )


def list_profiles(game: Game, session: Session) -> list[ProfileOut]:
    """Return all profiles for a game."""
    profiles = session.exec(select(Profile).where(Profile.game_id == game.id)).all()
    return [profile_to_out(p, game, session) for p in profiles]


def create_profile(game: Game, data: ProfileCreate, session: Session) -> ProfileOut:
    """Save a profile capturing current installed mods and their enabled state."""
    existing = session.exec(
        select(Profile).where(Profile.game_id == game.id, Profile.name == data.name)
    ).first()
    if existing:
        if game.active_profile_id == existing.id:
            game.active_profile_id = None
            session.add(game)
        session.delete(existing)
        session.flush()

    profile = Profile(
        game_id=game.id,  # type: ignore[arg-type]
        name=data.name,
        description=data.description,
    )
    session.add(profile)
    session.flush()

    installed = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()

    for mod in installed:
        entry = ProfileEntry(
            profile_id=profile.id,  # type: ignore[arg-type]
            installed_mod_id=mod.id,  # type: ignore[arg-type]
            enabled=not mod.disabled,
        )
        session.add(entry)

    session.commit()
    session.refresh(profile)

    return profile_to_out(profile, game, session)


def delete_profile(profile: Profile, game: Game, session: Session) -> None:
    """Delete a profile and its entries. Clear active if this was the active profile."""
    if game.active_profile_id == profile.id:
        game.active_profile_id = None
        session.add(game)
    session.delete(profile)
    session.commit()


def preview_profile(profile: Profile, game: Game, session: Session) -> ProfileDiffOut:
    """Compute diff between a profile and the current installed state without applying."""
    _ = profile.entries
    profile_state: dict[int, bool] = {}
    profile_mod_names: dict[int, str] = {}
    for entry in profile.entries:
        profile_state[entry.installed_mod_id] = entry.enabled
        installed = session.get(InstalledMod, entry.installed_mod_id)
        if installed:
            profile_mod_names[entry.installed_mod_id] = installed.name

    installed = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()
    installed_map = {m.id: m for m in installed}

    entries: list[ProfileDiffEntry] = []
    enable_count = disable_count = missing_count = unchanged_count = 0

    for mod_id, should_enable in profile_state.items():
        mod = installed_map.get(mod_id)
        if mod is None:
            mod_name = profile_mod_names.get(mod_id, f"Unknown (ID {mod_id})")
            entries.append(
                ProfileDiffEntry(
                    mod_name=mod_name,
                    installed_mod_id=mod_id,
                    action="missing",
                )
            )
            missing_count += 1
            continue

        is_currently_enabled = not mod.disabled
        if should_enable == is_currently_enabled:
            entries.append(
                ProfileDiffEntry(
                    mod_name=mod.name,
                    installed_mod_id=mod.id,  # type: ignore[arg-type]
                    action="unchanged",
                )
            )
            unchanged_count += 1
        elif should_enable:
            entries.append(
                ProfileDiffEntry(
                    mod_name=mod.name,
                    installed_mod_id=mod.id,  # type: ignore[arg-type]
                    action="enable",
                )
            )
            enable_count += 1
        else:
            entries.append(
                ProfileDiffEntry(
                    mod_name=mod.name,
                    installed_mod_id=mod.id,  # type: ignore[arg-type]
                    action="disable",
                )
            )
            disable_count += 1

    # Mods installed now but not in profile → will be disabled
    for mod in installed:
        if mod.id not in profile_state:
            if not mod.disabled:
                entries.append(
                    ProfileDiffEntry(
                        mod_name=mod.name,
                        installed_mod_id=mod.id,  # type: ignore[arg-type]
                        action="disable",
                    )
                )
                disable_count += 1
            else:
                entries.append(
                    ProfileDiffEntry(
                        mod_name=mod.name,
                        installed_mod_id=mod.id,  # type: ignore[arg-type]
                        action="unchanged",
                    )
                )
                unchanged_count += 1

    return ProfileDiffOut(
        profile_name=profile.name,
        entries=entries,
        enable_count=enable_count,
        disable_count=disable_count,
        missing_count=missing_count,
        unchanged_count=unchanged_count,
    )


def load_profile(profile: Profile, game: Game, session: Session) -> ProfileLoadResult:
    """Apply a profile: enable/disable mods to match the saved state."""
    _ = profile.entries
    mod_state: dict[int, bool] = {}
    profile_mod_names: dict[int, str] = {}
    for entry in profile.entries:
        mod_state[entry.installed_mod_id] = entry.enabled
        inst = session.get(InstalledMod, entry.installed_mod_id)
        if inst:
            profile_mod_names[entry.installed_mod_id] = inst.name

    installed = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()
    installed_ids = {m.id for m in installed}

    skipped: list[SkippedMod] = []
    for mod_id in mod_state:
        if mod_id not in installed_ids:
            skipped.append(
                SkippedMod(
                    name=profile_mod_names.get(mod_id, f"Unknown (ID {mod_id})"),
                    installed_mod_id=mod_id,
                )
            )

    for mod in installed:
        should_be_enabled = mod_state.get(mod.id, False)  # type: ignore[arg-type]
        is_currently_enabled = not mod.disabled
        if should_be_enabled != is_currently_enabled:
            toggle_mod(mod, game, session, commit=False)

    profile.last_loaded_at = datetime.now(UTC)
    game.active_profile_id = profile.id
    session.add(profile)
    session.add(game)
    session.commit()
    session.refresh(profile)
    session.refresh(game)

    return ProfileLoadResult(
        profile=profile_to_out(profile, game, session),
        skipped_mods=skipped,
        skipped_count=len(skipped),
    )


def export_profile(profile: Profile, game: Game, session: Session) -> ProfileExport:
    """Export a profile as a portable JSON-serialisable object."""
    _ = profile.entries
    mods: list[ProfileExportMod] = []
    for entry in profile.entries:
        installed = session.get(InstalledMod, entry.installed_mod_id)
        if installed:
            mods.append(
                ProfileExportMod(
                    name=installed.name,
                    nexus_mod_id=installed.nexus_mod_id,
                    version=installed.installed_version,
                    source_archive=installed.source_archive,
                    enabled=entry.enabled,
                )
            )

    return ProfileExport(
        profile_name=profile.name,
        game_name=game.name,
        exported_at=datetime.now(UTC),
        mod_count=len(mods),
        mods=mods,
    )


def import_profile(
    game: Game,
    data: ProfileExport,
    session: Session,
) -> ProfileImportResult:
    """Import a profile from an exported JSON, matching by name or nexus_mod_id."""
    existing = session.exec(
        select(Profile).where(Profile.game_id == game.id, Profile.name == data.profile_name)
    ).first()
    if existing:
        if game.active_profile_id == existing.id:
            game.active_profile_id = None
            session.add(game)
        session.delete(existing)
        session.flush()

    profile = Profile(
        game_id=game.id,  # type: ignore[arg-type]
        name=data.profile_name,
    )
    session.add(profile)
    session.flush()

    installed = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()

    name_map = {m.name.lower(): m for m in installed}
    nexus_map: dict[int, InstalledMod] = {}
    for m in installed:
        if m.nexus_mod_id is not None:
            nexus_map[m.nexus_mod_id] = m

    matched_count = 0
    skipped: list[SkippedMod] = []

    for export_mod in data.mods:
        matched = name_map.get(export_mod.name.lower())
        if not matched and export_mod.nexus_mod_id:
            matched = nexus_map.get(export_mod.nexus_mod_id)

        if matched:
            entry = ProfileEntry(
                profile_id=profile.id,  # type: ignore[arg-type]
                installed_mod_id=matched.id,  # type: ignore[arg-type]
                enabled=export_mod.enabled,
            )
            session.add(entry)
            matched_count += 1
        else:
            skipped.append(SkippedMod(name=export_mod.name))

    session.commit()
    session.refresh(profile)

    return ProfileImportResult(
        profile=profile_to_out(profile, game, session),
        matched_count=matched_count,
        skipped_mods=skipped,
        skipped_count=len(skipped),
    )


def update_profile(
    profile: Profile, data: ProfileUpdate, game: Game, session: Session
) -> ProfileOut:
    """Update profile name and/or description."""
    if data.name is not None:
        dupe = session.exec(
            select(Profile).where(
                Profile.game_id == game.id,
                Profile.name == data.name,
                Profile.id != profile.id,
            )
        ).first()
        if dupe:
            raise HTTPException(409, "A profile with that name already exists")
        profile.name = data.name
    if data.description is not None:
        profile.description = data.description
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile_to_out(profile, game, session)


def duplicate_profile(source: Profile, new_name: str, game: Game, session: Session) -> ProfileOut:
    """Clone a profile with all its entries under a new name."""
    existing = session.exec(
        select(Profile).where(Profile.game_id == game.id, Profile.name == new_name)
    ).first()
    if existing:
        raise HTTPException(409, "A profile with that name already exists")

    _ = source.entries
    clone = Profile(
        game_id=source.game_id,
        name=new_name,
        description=source.description,
    )
    session.add(clone)
    session.flush()

    for entry in source.entries:
        session.add(
            ProfileEntry(
                profile_id=clone.id,  # type: ignore[arg-type]
                installed_mod_id=entry.installed_mod_id,
                enabled=entry.enabled,
            )
        )

    session.commit()
    session.refresh(clone)
    return profile_to_out(clone, game, session)


def compare_profiles(
    profile_a: Profile, profile_b: Profile, game: Game, session: Session
) -> ProfileCompareOut:
    """Compare two profiles and return entries grouped by membership."""
    _ = profile_a.entries
    _ = profile_b.entries

    a_map: dict[int, bool] = {e.installed_mod_id: e.enabled for e in profile_a.entries}
    b_map: dict[int, bool] = {e.installed_mod_id: e.enabled for e in profile_b.entries}

    a_ids = set(a_map.keys())
    b_ids = set(b_map.keys())

    all_ids = list(a_ids | b_ids)
    all_mods = (
        session.exec(select(InstalledMod).where(InstalledMod.id.in_(all_ids))).all()
        if all_ids
        else []
    )
    name_map = {m.id: m.name for m in all_mods}

    def _mod_name(mod_id: int) -> str:
        return name_map.get(mod_id, f"Unknown (ID {mod_id})")

    only_a: list[ProfileCompareEntry] = []
    for mod_id in sorted(a_ids - b_ids):
        only_a.append(
            ProfileCompareEntry(
                mod_name=_mod_name(mod_id),
                installed_mod_id=mod_id,
                enabled_in_a=a_map[mod_id],
                enabled_in_b=None,
            )
        )

    only_b: list[ProfileCompareEntry] = []
    for mod_id in sorted(b_ids - a_ids):
        only_b.append(
            ProfileCompareEntry(
                mod_name=_mod_name(mod_id),
                installed_mod_id=mod_id,
                enabled_in_a=None,
                enabled_in_b=b_map[mod_id],
            )
        )

    in_both: list[ProfileCompareEntry] = []
    for mod_id in sorted(a_ids & b_ids):
        in_both.append(
            ProfileCompareEntry(
                mod_name=_mod_name(mod_id),
                installed_mod_id=mod_id,
                enabled_in_a=a_map[mod_id],
                enabled_in_b=b_map[mod_id],
            )
        )

    return ProfileCompareOut(
        profile_a_name=profile_a.name,
        profile_b_name=profile_b.name,
        only_in_a=only_a,
        only_in_b=only_b,
        in_both=in_both,
        only_in_a_count=len(only_a),
        only_in_b_count=len(only_b),
        in_both_count=len(in_both),
    )
