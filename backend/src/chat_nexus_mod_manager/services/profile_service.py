"""Profile management: save, load, export, and import mod configurations.

A profile captures which installed mods are enabled for a specific game.
Profiles can be exported to a portable JSON format for sharing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.install import InstalledMod
from chat_nexus_mod_manager.models.profile import Profile, ProfileEntry
from chat_nexus_mod_manager.schemas.profile import (
    ProfileCreate,
    ProfileExport,
    ProfileExportMod,
    ProfileModOut,
    ProfileOut,
)
from chat_nexus_mod_manager.services.install_service import toggle_mod


def list_profiles(game: Game, session: Session) -> list[ProfileOut]:
    """Return all profiles for a game."""
    profiles = session.exec(select(Profile).where(Profile.game_id == game.id)).all()
    result: list[ProfileOut] = []
    for p in profiles:
        _ = p.entries
        mods: list[ProfileModOut] = []
        for e in p.entries:
            _ = e.installed_mod
            if e.installed_mod:
                mods.append(
                    ProfileModOut(
                        installed_mod_id=e.installed_mod_id,
                        name=e.installed_mod.name,
                        enabled=e.enabled,
                    )
                )
        result.append(
            ProfileOut(
                id=p.id,  # type: ignore[arg-type]
                name=p.name,
                game_id=p.game_id,
                created_at=p.created_at,
                mod_count=len(mods),
                mods=mods,
            )
        )
    return result


def create_profile(game: Game, data: ProfileCreate, session: Session) -> ProfileOut:
    """Save a profile capturing current installed mods and their enabled state."""
    existing = session.exec(
        select(Profile).where(Profile.game_id == game.id, Profile.name == data.name)
    ).first()
    if existing:
        session.delete(existing)
        session.flush()

    profile = Profile(game_id=game.id, name=data.name)  # type: ignore[arg-type]
    session.add(profile)
    session.flush()

    installed = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()

    mods: list[ProfileModOut] = []
    for mod in installed:
        entry = ProfileEntry(
            profile_id=profile.id,  # type: ignore[arg-type]
            installed_mod_id=mod.id,  # type: ignore[arg-type]
            enabled=not mod.disabled,
        )
        session.add(entry)
        mods.append(
            ProfileModOut(
                installed_mod_id=mod.id,  # type: ignore[arg-type]
                name=mod.name,
                enabled=not mod.disabled,
            )
        )

    session.commit()
    session.refresh(profile)

    return ProfileOut(
        id=profile.id,  # type: ignore[arg-type]
        name=profile.name,
        game_id=profile.game_id,
        created_at=profile.created_at,
        mod_count=len(mods),
        mods=mods,
    )


def delete_profile(profile: Profile, session: Session) -> None:
    """Delete a profile and its entries."""
    session.delete(profile)
    session.commit()


def load_profile(profile: Profile, game: Game, session: Session) -> ProfileOut:
    """Apply a profile: enable/disable mods to match the saved state."""
    _ = profile.entries
    mod_state: dict[int, bool] = {}
    for entry in profile.entries:
        mod_state[entry.installed_mod_id] = entry.enabled

    installed = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()

    for mod in installed:
        should_be_enabled = mod_state.get(mod.id, False)  # type: ignore[arg-type]
        is_currently_enabled = not mod.disabled

        if should_be_enabled != is_currently_enabled:
            toggle_mod(mod, game, session)

    return _profile_to_out(profile, session)


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
) -> ProfileOut:
    """Import a profile from an exported JSON, matching by name or nexus_mod_id."""
    profile_data = ProfileCreate(name=data.profile_name)

    existing = session.exec(
        select(Profile).where(Profile.game_id == game.id, Profile.name == data.profile_name)
    ).first()
    if existing:
        session.delete(existing)
        session.flush()

    profile = Profile(game_id=game.id, name=profile_data.name)  # type: ignore[arg-type]
    session.add(profile)
    session.flush()

    installed = session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()

    name_map = {m.name.lower(): m for m in installed}
    nexus_map: dict[int, InstalledMod] = {}
    for m in installed:
        if m.nexus_mod_id is not None:
            nexus_map[m.nexus_mod_id] = m

    mods_out: list[ProfileModOut] = []
    for export_mod in data.mods:
        matched = name_map.get(export_mod.name.lower())
        if not matched and export_mod.nexus_mod_id:
            matched = nexus_map.get(export_mod.nexus_mod_id)

        if matched:
            entry = ProfileEntry(
                profile_id=profile.id,  # type: ignore[arg-type]
                installed_mod_id=matched.id,  # type: ignore[arg-type]
                enabled=True,
            )
            session.add(entry)
            mods_out.append(
                ProfileModOut(
                    installed_mod_id=matched.id,  # type: ignore[arg-type]
                    name=matched.name,
                    enabled=True,
                )
            )

    session.commit()
    session.refresh(profile)

    return ProfileOut(
        id=profile.id,  # type: ignore[arg-type]
        name=profile.name,
        game_id=profile.game_id,
        created_at=profile.created_at,
        mod_count=len(mods_out),
        mods=mods_out,
    )


def _profile_to_out(profile: Profile, session: Session) -> ProfileOut:
    """Convert a Profile model to a ProfileOut schema."""
    _ = profile.entries
    mods: list[ProfileModOut] = []
    for entry in profile.entries:
        installed = session.get(InstalledMod, entry.installed_mod_id)
        if installed:
            mods.append(
                ProfileModOut(
                    installed_mod_id=entry.installed_mod_id,
                    name=installed.name,
                    enabled=entry.enabled,
                )
            )
    return ProfileOut(
        id=profile.id,  # type: ignore[arg-type]
        name=profile.name,
        game_id=profile.game_id,
        created_at=profile.created_at,
        mod_count=len(mods),
        mods=mods,
    )
