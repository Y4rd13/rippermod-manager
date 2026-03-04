from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from rippermod_manager.database import get_session
from rippermod_manager.models.settings import AppSetting, PCSpecs
from rippermod_manager.schemas.settings import PCSpecsOut, SettingOut, SettingsUpdate
from rippermod_manager.services.keyring_service import SECRET_KEYS, get_secret
from rippermod_manager.services.settings_helpers import set_setting

router = APIRouter(prefix="/settings", tags=["settings"])

HIDDEN_KEYS = {"nexus_api_key", "openai_api_key"}


def _mask_secret(value: str) -> str:
    """Return a partially masked version of a secret value."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * min(len(value) - 8, 20)}{value[-4:]}"


@router.get("/", response_model=list[SettingOut])
def list_settings(session: Session = Depends(get_session)) -> list[SettingOut]:
    settings = session.exec(select(AppSetting)).all()
    result: list[SettingOut] = []
    seen_keys: set[str] = set()
    for s in settings:
        seen_keys.add(s.key)
        value = s.value
        if s.key in SECRET_KEYS and not value:
            value = get_secret(s.key) or ""
        if s.key in HIDDEN_KEYS and value:
            value = _mask_secret(value)
        result.append(SettingOut(key=s.key, value=value))
    for sk in SECRET_KEYS:
        if sk not in seen_keys:
            kr_val = get_secret(sk) or ""
            if kr_val:
                result.append(SettingOut(
                    key=sk,
                    value=_mask_secret(kr_val) if sk in HIDDEN_KEYS else kr_val,
                ))
    return result


@router.put("/", response_model=list[SettingOut])
def update_settings(
    data: SettingsUpdate, session: Session = Depends(get_session)
) -> list[SettingOut]:
    results: list[SettingOut] = []
    for key, value in data.settings.items():
        if key in SECRET_KEYS:
            set_setting(session, key, value)
        else:
            setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
            if setting:
                setting.value = value
            else:
                session.add(AppSetting(key=key, value=value))
        results.append(
            SettingOut(
                key=key,
                value=_mask_secret(value) if key in HIDDEN_KEYS and value else value,
            )
        )
    session.commit()
    return results


@router.get("/specs", response_model=PCSpecsOut | None)
def get_specs(session: Session = Depends(get_session)) -> PCSpecs | None:
    return session.exec(
        select(PCSpecs).order_by(PCSpecs.captured_at.desc())  # type: ignore[arg-type]
    ).first()


@router.post("/specs/capture", response_model=PCSpecsOut)
def capture_specs(data: PCSpecsOut, session: Session = Depends(get_session)) -> PCSpecs:
    specs = PCSpecs(**data.model_dump())
    session.add(specs)
    session.commit()
    session.refresh(specs)
    return specs
