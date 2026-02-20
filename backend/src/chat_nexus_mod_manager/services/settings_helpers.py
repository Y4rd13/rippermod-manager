"""Helpers for reading app settings from the database."""

from sqlmodel import Session, select

from chat_nexus_mod_manager.models.settings import AppSetting


def get_setting(session: Session, key: str) -> str | None:
    """Read a single setting value by key, returning None if missing or empty."""
    setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    return setting.value if setting and setting.value else None


def set_setting(session: Session, key: str, value: str) -> None:
    """Upsert a single setting value by key. Caller controls commit."""
    setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    if setting:
        setting.value = value
    else:
        session.add(AppSetting(key=key, value=value))
