import logging
from dataclasses import dataclass

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusModRequirement
from rippermod_manager.schemas.deploy import DriftReport

logger = logging.getLogger(__name__)


@dataclass
class HealthIssue:
    kind: str
    severity: str  # critical | warning | info
    message: str
    suggested_fix: str = ""
    mod_name: str = ""
    installed_mod_id: int | None = None


def check_health(game: Game, session: Session) -> list[HealthIssue]:
    """Scan the current setup for the problems that most often break a launch.

    Read-only and offline: reuses already-synced requirement data, the cached
    update check, and VFS drift detection. No Nexus calls.
    """
    installed = list(
        session.exec(select(InstalledMod).where(InstalledMod.game_id == game.id)).all()
    )
    drift = _safe_drift(game, session)
    issues: list[HealthIssue] = []
    issues += _check_requirements(installed, session)
    issues += _check_outdated(game, session)
    issues += _check_install_integrity(installed, drift)
    issues += _check_foreign_and_untracked(game, installed, drift, session)
    return issues


def _safe_drift(game: Game, session: Session) -> DriftReport | None:
    from rippermod_manager.services.vfs.deploy_service import detect_drift

    try:
        return detect_drift(game, session)
    except OSError:
        logger.warning("Health check: drift detection failed", exc_info=True)
        return None


def _check_requirements(installed: list[InstalledMod], session: Session) -> list[HealthIssue]:
    by_nexus = {m.nexus_mod_id: m for m in installed if m.nexus_mod_id is not None}
    enabled_nexus = {nid for nid, m in by_nexus.items() if not m.disabled}
    enabled_ids = [
        m.nexus_mod_id for m in installed if m.nexus_mod_id is not None and not m.disabled
    ]
    if not enabled_ids:
        return []
    # One batch query instead of a SELECT per mod (health runs on every launch).
    all_reqs = session.exec(
        select(NexusModRequirement).where(
            NexusModRequirement.nexus_mod_id.in_(enabled_ids),  # type: ignore[union-attr]
            NexusModRequirement.is_reverse.is_(False),  # type: ignore[union-attr]
            NexusModRequirement.is_external.is_(False),  # type: ignore[union-attr]
        )
    ).all()
    reqs_by_mod: dict[int, list[NexusModRequirement]] = {}
    for r in all_reqs:
        reqs_by_mod.setdefault(r.nexus_mod_id, []).append(r)

    issues: list[HealthIssue] = []
    for mod in installed:
        if mod.disabled or mod.nexus_mod_id is None:
            continue
        for r in reqs_by_mod.get(mod.nexus_mod_id, []):
            if r.required_mod_id is None:
                continue
            if r.required_mod_id not in by_nexus:
                issues.append(
                    HealthIssue(
                        kind="missing_requirement",
                        severity="critical",
                        mod_name=mod.name,
                        message=f'requires "{r.mod_name}", which is not installed.',
                        suggested_fix=f"Install {r.mod_name} from Nexus Mods.",
                        installed_mod_id=mod.id,
                    )
                )
            elif r.required_mod_id not in enabled_nexus:
                issues.append(
                    HealthIssue(
                        kind="disabled_requirement",
                        severity="warning",
                        mod_name=mod.name,
                        message=f'requires "{r.mod_name}", which is installed but disabled.',
                        suggested_fix=f"Enable {r.mod_name}.",
                        installed_mod_id=mod.id,
                    )
                )
    return issues


def _check_outdated(game: Game, session: Session) -> list[HealthIssue]:
    from rippermod_manager.services.update_service import check_cached_updates

    result = check_cached_updates(game.id, game.domain_name, session)
    issues: list[HealthIssue] = []
    for u in result.updates:
        issues.append(
            HealthIssue(
                kind="outdated",
                severity="info",
                mod_name=u.get("display_name") or "A mod",
                message=u.get("reason") or "A newer version is available.",
                suggested_fix="Update it from the Updates tab.",
                installed_mod_id=u.get("installed_mod_id"),
            )
        )
    return issues


def _check_install_integrity(
    installed: list[InstalledMod], drift: DriftReport | None
) -> list[HealthIssue]:
    by_id = {m.id: m for m in installed}
    unhealthy: dict[int, str] = {}
    for m in installed:
        if not m.disabled and not m.deployed and m.id is not None:
            unhealthy[m.id] = (
                "is enabled but not deployed -- its files aren't linked into the game."
            )
    if drift is not None:
        for mod_id, counts in drift.by_mod.items():
            if counts.get("missing", 0) > 0:
                unhealthy[mod_id] = (
                    f"has {counts['missing']} deployed file(s) missing from the game folder."
                )
    issues: list[HealthIssue] = []
    for mod_id, msg in unhealthy.items():
        m = by_id.get(mod_id)
        issues.append(
            HealthIssue(
                kind="failed_install",
                severity="warning",
                mod_name=m.name if m else f"Mod {mod_id}",
                message=msg,
                suggested_fix="Re-deploy mods from the game page.",
                installed_mod_id=mod_id,
            )
        )
    return issues


def _check_foreign_and_untracked(
    game: Game,
    installed: list[InstalledMod],
    drift: DriftReport | None,
    session: Session,
) -> list[HealthIssue]:
    by_id = {m.id: m for m in installed}
    issues: list[HealthIssue] = []
    if drift is not None:
        for mod_id, counts in drift.by_mod.items():
            if counts.get("foreign", 0) > 0:
                m = by_id.get(mod_id)
                issues.append(
                    HealthIssue(
                        kind="foreign_files",
                        severity="warning",
                        mod_name=m.name if m else f"Mod {mod_id}",
                        message=(
                            f"has {counts['foreign']} file(s) at its destinations that "
                            "aren't managed here (overwritten by another source)."
                        ),
                        suggested_fix="Re-deploy (force) to restore managed links.",
                        installed_mod_id=mod_id,
                    )
                )
    try:
        from rippermod_manager.services.vfs.untracked import find_untracked_files

        untracked = find_untracked_files(game, session)
    except OSError:
        logger.warning("Health check: untracked scan failed", exc_info=True)
        untracked = []
    if untracked:
        issues.append(
            HealthIssue(
                kind="untracked_files",
                severity="info",
                message=(
                    f"{len(untracked)} file(s) in the game folder aren't managed by any "
                    "installed mod."
                ),
                suggested_fix="Review them on the game page (manual or other-manager installs).",
            )
        )
    return issues
