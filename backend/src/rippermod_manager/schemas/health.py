from pydantic import BaseModel


class HealthIssueOut(BaseModel):
    # kind: missing_requirement | disabled_requirement |
    #       failed_install | misplaced_files | foreign_files | untracked_files
    kind: str
    severity: str  # critical | warning | info
    message: str
    suggested_fix: str = ""
    mod_name: str = ""
    installed_mod_id: int | None = None
    # Optional action targets so the UI can offer a one-click fix:
    nexus_url: str | None = None  # missing_requirement -> the required mod's Nexus page
    action_mod_id: int | None = None  # disabled_requirement -> the mod to enable
    required_name: str = ""  # missing/disabled_requirement -> the required mod's name


class HealthReport(BaseModel):
    issues: list[HealthIssueOut]
    critical: int
    warning: int
    info: int
    ok: bool  # True when there are no critical issues (warnings/info don't block launch)
