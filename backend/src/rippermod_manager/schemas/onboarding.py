from pydantic import BaseModel


class OnboardingStatus(BaseModel):
    completed: bool
    current_step: int
    has_nexus_key: bool
    has_game: bool


class OnboardingComplete(BaseModel):
    pass
