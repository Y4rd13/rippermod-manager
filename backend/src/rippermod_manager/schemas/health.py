from pydantic import BaseModel


class HealthIssueOut(BaseModel):
    # kind: missing_requirement | disabled_requirement | outdated |
    #       failed_install | foreign_files | untracked_files
    kind: str
    severity: str  # critical | warning | info
    message: str
    suggested_fix: str = ""
    mod_name: str = ""
    installed_mod_id: int | None = None


class HealthReport(BaseModel):
    issues: list[HealthIssueOut]
    critical: int
    warning: int
    info: int
    ok: bool  # True when there are no critical issues (warnings/info don't block launch)
