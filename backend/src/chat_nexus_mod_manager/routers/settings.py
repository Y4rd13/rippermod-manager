from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.settings import AppSetting, PCSpecs
from chat_nexus_mod_manager.schemas.settings import PCSpecsOut, SettingOut, SettingsUpdate

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
    return [
        SettingOut(
            key=s.key,
            value=_mask_secret(s.value) if s.key in HIDDEN_KEYS and s.value else s.value,
        )
        for s in settings
    ]


@router.put("/", response_model=list[SettingOut])
def update_settings(
    data: SettingsUpdate, session: Session = Depends(get_session)
) -> list[SettingOut]:
    results: list[SettingOut] = []
    for key, value in data.settings.items():
        setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
        if setting:
            setting.value = value
        else:
            setting = AppSetting(key=key, value=value)
            session.add(setting)
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
