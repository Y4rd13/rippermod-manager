from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from rippermod_manager.database import get_session
from rippermod_manager.models.game import Game
from rippermod_manager.models.settings import AppSetting
from rippermod_manager.schemas.onboarding import OnboardingComplete, OnboardingStatus
from rippermod_manager.services.keyring_service import SECRET_KEYS, delete_secret, get_secret
from rippermod_manager.services.settings_helpers import set_setting

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _has_key(session: Session, key_name: str) -> bool:
    if key_name in SECRET_KEYS and get_secret(key_name):
        return True
    setting = session.exec(select(AppSetting).where(AppSetting.key == key_name)).first()
    return bool(setting and setting.value)


@router.get("/status", response_model=OnboardingStatus)
def get_onboarding_status(
    session: Session = Depends(get_session),
) -> OnboardingStatus:
    has_openai = _has_key(session, "openai_api_key")
    has_nexus = _has_key(session, "nexus_api_key")
    has_game = session.exec(select(Game)).first() is not None

    completed_setting = session.exec(
        select(AppSetting).where(AppSetting.key == "onboarding_completed")
    ).first()
    completed = bool(completed_setting and completed_setting.value == "true")

    step = 0
    if has_nexus:
        step = 2
    if has_game:
        step = 3
    if completed:
        step = 4

    return OnboardingStatus(
        completed=completed,
        current_step=step,
        has_openai_key=has_openai,
        has_nexus_key=has_nexus,
        has_game=has_game,
    )


@router.post("/complete", response_model=OnboardingStatus)
def complete_onboarding(
    data: OnboardingComplete, session: Session = Depends(get_session)
) -> OnboardingStatus:
    if data.openai_api_key:
        set_setting(session, "openai_api_key", data.openai_api_key)

    completed_setting = session.exec(
        select(AppSetting).where(AppSetting.key == "onboarding_completed")
    ).first()
    if completed_setting:
        completed_setting.value = "true"
    else:
        session.add(AppSetting(key="onboarding_completed", value="true"))

    session.commit()
    return get_onboarding_status(session)


@router.post("/reset", response_model=OnboardingStatus)
def reset_onboarding(session: Session = Depends(get_session)) -> OnboardingStatus:
    """Clear Nexus API key and reset onboarding so the user can reconnect."""
    delete_secret("nexus_api_key")

    for key in ("nexus_api_key", "nexus_username", "nexus_is_premium"):
        setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
        if setting:
            session.delete(setting)

    completed = session.exec(
        select(AppSetting).where(AppSetting.key == "onboarding_completed")
    ).first()
    if completed:
        completed.value = "false"

    session.commit()
    return get_onboarding_status(session)
