from pydantic import BaseModel


class OnboardingStatus(BaseModel):
    completed: bool
    current_step: int
    has_openai_key: bool
    has_nexus_key: bool
    has_game: bool


class OnboardingComplete(BaseModel):
    openai_api_key: str = ""
    nexus_api_key: str = ""
