"""Helpers for reading app settings from the database with keyring fallback."""

from sqlmodel import Session, select

from rippermod_manager.models.settings import AppSetting
from rippermod_manager.services.keyring_service import SECRET_KEYS, get_secret, set_secret


def get_setting(session: Session, key: str) -> str | None:
    """Read a single setting value by key, returning None if missing or empty.

    For secret keys, checks the OS keychain first and falls back to SQLite.
    """
    if key in SECRET_KEYS:
        kr_val = get_secret(key)
        if kr_val:
            return kr_val
    setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    return setting.value if setting and setting.value else None


def set_setting(session: Session, key: str, value: str) -> None:
    """Upsert a single setting value by key. Caller controls commit.

    For secret keys, writes to the OS keychain if available and clears
    the SQLite value on success.
    """
    stored_in_keyring = False
    if key in SECRET_KEYS:
        stored_in_keyring = set_secret(key, value)

    setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    if setting:
        setting.value = "" if stored_in_keyring else value
    else:
        session.add(AppSetting(key=key, value="" if stored_in_keyring else value))
