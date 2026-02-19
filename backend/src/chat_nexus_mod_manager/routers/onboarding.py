from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.game import Game
from chat_nexus_mod_manager.models.settings import AppSetting
from chat_nexus_mod_manager.schemas.onboarding import OnboardingComplete, OnboardingStatus

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _has_key(session: Session, key_name: str) -> bool:
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
    if has_openai:
        step = 1
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
    for key, value in [
        ("openai_api_key", data.openai_api_key),
        ("nexus_api_key", data.nexus_api_key),
    ]:
        if value:
            setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
            if setting:
                setting.value = value
            else:
                session.add(AppSetting(key=key, value=value))

    completed_setting = session.exec(
        select(AppSetting).where(AppSetting.key == "onboarding_completed")
    ).first()
    if completed_setting:
        completed_setting.value = "true"
    else:
        session.add(AppSetting(key="onboarding_completed", value="true"))

    session.commit()
    return get_onboarding_status(session)
