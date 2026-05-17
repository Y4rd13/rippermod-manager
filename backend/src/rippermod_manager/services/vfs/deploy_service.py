"""Orchestrates VFS deployment: planning, journaling, execution."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import (  # noqa: F401 used in plan_deploy
    DeployJournalEntry,
    InstalledMod,
    InstalledModFile,
)
from rippermod_manager.schemas.deploy import (
    DeployOp,
    DeployOpResult,
    DeployPlan,
    DeployReport,
    DriftReport,
    PreflightReport,
    RedmodDeployResult,
)
from rippermod_manager.services.vfs.primitives import (
    VfsError,
    hardlink,
    is_game_running,
    junction,
    probe_hardlink_support,
    remove_junction,
    same_volume,
    unlink,
    verify_link,
)

logger = logging.getLogger(__name__)

GAME_EXE = "Cyberpunk2077.exe"
REDMOD_REL_PATH = Path("tools") / "redmod" / "bin" / "redMod.exe"
REDMOD_TIMEOUT_S = 600  # generous: heavy REDmod sets can take several minutes to compile


def pre_flight_check(game: Game) -> PreflightReport:
    report = PreflightReport()
    install = Path(game.install_path)
    staging = install / "downloaded_mods"
    staging.mkdir(parents=True, exist_ok=True)

    if is_game_running(GAME_EXE):
        report.ok = False
        report.game_running = True
        report.reasons.append("Cyberpunk 2077 is running — close it before deploying.")

    try:
        sv = same_volume(staging, install)
    except (OSError, VfsError) as exc:
        sv = False
        report.reasons.append(f"could not check volume: {exc}")
    report.same_volume = sv
    if not sv:
        report.ok = False
        report.reasons.append(
            "Staging dir and game dir are on different volumes; hardlinks require same volume."
        )

    try:
        report.hardlink_supported = probe_hardlink_support(staging, install)
    except (OSError, VfsError) as exc:
        report.hardlink_supported = False
        report.reasons.append(f"hardlink probe failed: {exc}")
    if not report.hardlink_supported:
        report.ok = False
        report.reasons.append("Filesystem does not support hardlinks (NTFS required).")

    try:
        report.free_disk_bytes = shutil.disk_usage(install).free
    except OSError:
        report.free_disk_bytes = 0

    return report


def plan_deploy(game: Game, session: Session) -> tuple[DeployPlan, int]:
    """Build a DeployPlan from the installed-mod manifest for a game.

    Enumerates all enabled InstalledMod rows and their InstalledModFile rows,
    producing one DeployOp per file (link) or per REDmod subtree root (junction).
    Junction ops are deduplicated: only one junction per mods/<name> directory.

    Hardlink and junction ops are skipped when the destination already matches
    the staged source (idempotent re-deploy). Returns the plan plus the count of
    skipped ops so callers can surface "already up to date" without false drift.
    """
    install = Path(game.install_path)
    staging_root = install / "downloaded_mods"

    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.disabled.is_(False),  # type: ignore[union-attr]
        )
    ).all()

    plan = DeployPlan(game_id=game.id)
    junction_dirs_seen: set[str] = set()
    skipped_existing = 0

    for mod in mods:
        _ = mod.files  # touch relationship to load files
        for f in mod.files:
            src = staging_root / mod.staging_dir / f.source_path.replace("\\", "/")
            dst = install / f.relative_path.replace("\\", "/")
            if f.link_kind == "junction":
                parts = f.relative_path.replace("\\", "/").split("/")
                if len(parts) >= 2 and parts[0] == "mods":
                    redmod_dst = install / "mods" / parts[1]
                    redmod_src = staging_root / mod.staging_dir / "mods" / parts[1]
                    key = str(redmod_dst)
                    if key in junction_dirs_seen:
                        continue
                    junction_dirs_seen.add(key)
                    # Idempotency: junction already in place (any reparse-point dir).
                    # We don't read reparse-point targets; presence is treated as ours.
                    if redmod_dst.is_dir():
                        skipped_existing += 1
                        continue
                    plan.ops.append(
                        DeployOp(
                            operation="junction",
                            src=str(redmod_src),
                            dst=str(redmod_dst),
                            installed_mod_id=mod.id,
                        )
                    )
                    continue
            # Idempotency: hardlink already points to the staged source.
            if verify_link(src, dst):
                skipped_existing += 1
                continue
            plan.ops.append(
                DeployOp(
                    operation="link",
                    src=str(src),
                    dst=str(dst),
                    installed_mod_id=mod.id,
                )
            )

    return plan, skipped_existing


def execute_plan(plan: DeployPlan, session: Session) -> DeployReport:
    """Run each op in `plan`, persisting a write-ahead journal entry before each
    filesystem mutation so crash recovery can roll back partial state on next start.
    """
    results: list[DeployOpResult] = []

    for op in plan.ops:
        # Write-ahead: persist 'pending' BEFORE the FS op so a crash mid-op leaves
        # a recoverable journal row. The end-of-loop commit covers status updates.
        entry = DeployJournalEntry(
            game_id=plan.game_id,
            operation=op.operation,
            src=op.src,
            dst=op.dst,
            status="pending",
        )
        session.add(entry)
        session.commit()

        try:
            if op.operation == "link":
                hardlink(Path(op.src), Path(op.dst))
            elif op.operation == "unlink":
                unlink(Path(op.dst))
            elif op.operation == "junction":
                junction(Path(op.src), Path(op.dst))
            elif op.operation == "rm_junction":
                remove_junction(Path(op.dst))
            else:
                raise VfsError(f"unknown op: {op.operation}")
            entry.status = "done"
            results.append(DeployOpResult(op=op, status="done"))
        except VfsError as exc:
            entry.status = "failed"
            entry.error = str(exc)
            results.append(DeployOpResult(op=op, status="failed", error=str(exc)))

        session.add(entry)

    session.commit()
    done = sum(1 for r in results if r.status == "done")
    failed = sum(1 for r in results if r.status == "failed")
    return DeployReport(total=len(results), done=done, failed=failed, results=results)


def undeploy(game: Game, session: Session) -> DeployReport:
    """Remove all deployed hardlinks/junctions for a game and mark mods as undeployed.

    Skips the full pre-flight because filesystem support gates are irrelevant when
    removing files. Only the cheap ``is_game_running`` check is enforced, and its
    outcome is surfaced on the returned report so callers can show why the action
    was refused.
    """
    if is_game_running(GAME_EXE):
        refuse_pre = PreflightReport(
            ok=False,
            game_running=True,
            reasons=["Cyberpunk 2077 is running — close it before undeploying."],
        )
        return DeployReport(total=0, done=0, failed=0, results=[], preflight=refuse_pre)

    install = Path(game.install_path)
    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.deployed.is_(True),  # type: ignore[union-attr]
        )
    ).all()

    ops: list[DeployOp] = []
    junction_dirs_seen: set[str] = set()
    for mod in mods:
        _ = mod.files  # touch relationship to load files
        for f in mod.files:
            dst = install / f.relative_path.replace("\\", "/")
            if f.link_kind == "junction":
                parts = f.relative_path.replace("\\", "/").split("/")
                if len(parts) >= 2 and parts[0] == "mods":
                    redmod_dst = install / "mods" / parts[1]
                    key = str(redmod_dst)
                    if key in junction_dirs_seen:
                        continue
                    junction_dirs_seen.add(key)
                    ops.append(
                        DeployOp(
                            operation="rm_junction",
                            src="",
                            dst=str(redmod_dst),
                            installed_mod_id=mod.id,
                        )
                    )
                    continue
            ops.append(
                DeployOp(
                    operation="unlink",
                    src="",
                    dst=str(dst),
                    installed_mod_id=mod.id,
                )
            )

    plan = DeployPlan(game_id=game.id, ops=ops)
    report = execute_plan(plan, session)

    if report.is_clean:
        for m in mods:
            m.deployed = False
            session.add(m)
        session.commit()
    return report


def detect_drift(game: Game, session: Session) -> DriftReport:
    install = Path(game.install_path)
    staging_root = install / "downloaded_mods"

    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.disabled.is_(False),  # type: ignore[union-attr]
        )
    ).all()

    total = linked = missing = foreign = 0
    by_mod: dict[int, dict[str, int]] = {}

    for mod in mods:
        _ = mod.files
        m_linked = m_missing = m_foreign = 0
        # Cache per-junction-root checks so we don't probe the same reparse point N times
        # for an N-file REDmod and so all files under the same root agree on linked/missing.
        junction_root_state: dict[Path, bool] = {}
        for f in mod.files:
            total += 1
            src = staging_root / mod.staging_dir / f.source_path.replace("\\", "/")
            rel = f.relative_path.replace("\\", "/")
            dst = install / rel
            if f.link_kind == "hardlink":
                if not dst.exists():
                    missing += 1
                    m_missing += 1
                elif verify_link(src, dst):
                    linked += 1
                    m_linked += 1
                else:
                    foreign += 1
                    m_foreign += 1
            elif f.link_kind == "junction":
                # The junction is at mods/<name>/; per-file paths resolve through it. Check
                # the root's reparse point once, then count every file under that root as
                # linked-or-missing based on that single check.
                parts = rel.split("/")
                if len(parts) >= 2 and parts[0] == "mods":
                    root = install / "mods" / parts[1]
                    if root not in junction_root_state:
                        junction_root_state[root] = root.is_dir()
                    if junction_root_state[root]:
                        linked += 1
                        m_linked += 1
                    else:
                        missing += 1
                        m_missing += 1
                else:
                    # Defensive: junction kind without expected mods/<name>/ layout. Fall
                    # back to a plain existence check so we still report something sane.
                    if dst.exists():
                        linked += 1
                        m_linked += 1
                    else:
                        missing += 1
                        m_missing += 1
        if mod.id is not None:
            by_mod[mod.id] = {"linked": m_linked, "missing": m_missing, "foreign": m_foreign}

    return DriftReport(total=total, linked=linked, missing=missing, foreign=foreign, by_mod=by_mod)


def _redmod_exe(game: Game) -> Path | None:
    """Return the REDmod binary path if available, else None.

    Pre-2.0 Cyberpunk installs and pirated/stripped copies may not ship the REDmod
    DLC, so we fall back to a no-op instead of erroring out.
    """
    p = Path(game.install_path) / REDMOD_REL_PATH
    return p if p.is_file() else None


def _has_enabled_redmods(game: Game, session: Session) -> bool:
    """Return True iff any enabled InstalledMod owns files under ``mods/``.

    Only mods with REDmod content require a compile pass; legacy archives,
    redscript, TweakXL and CET load directly from disk without one.
    """
    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.disabled.is_(False),  # type: ignore[union-attr]
        )
    ).all()
    for mod in mods:
        _ = mod.files
        for f in mod.files:
            if f.relative_path.replace("\\", "/").startswith("mods/"):
                return True
    return False


def redmod_deploy(game: Game) -> RedmodDeployResult:
    """Invoke ``redMod.exe deploy`` to compile the REDmod cache.

    Vortex runs this on its Deploy button; MO2 runs it pre-launch. We run it after
    every VFS deploy that touches REDmod content, because RipperMod launches the
    game with ``--launcher-skip`` (bypassing the REDlauncher's own auto-deploy).
    Without this step the game would load with a stale ``r6/cache/modded/`` and
    new REDmods would be silently ignored.

    The function is best-effort: an exit-code != 0, a timeout, or a missing binary
    is surfaced on the returned struct rather than raising, so the deploy report
    can still report the hardlink/junction state as successful.
    """
    exe = _redmod_exe(game)
    if exe is None:
        return RedmodDeployResult(ran=False, skipped_reason="REDmod binary not found")

    try:
        proc = subprocess.run(
            [str(exe), "deploy", "-reportProgress"],
            cwd=str(exe.parent),
            capture_output=True,
            text=True,
            timeout=REDMOD_TIMEOUT_S,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return RedmodDeployResult(
            ran=True,
            success=False,
            error=f"redmod deploy timed out after {REDMOD_TIMEOUT_S}s",
        )
    except OSError as exc:
        return RedmodDeployResult(ran=True, success=False, error=str(exc))

    success = proc.returncode == 0
    error = ""
    if not success:
        error = (proc.stderr or proc.stdout or "").strip() or "redmod deploy failed"
    return RedmodDeployResult(
        ran=True,
        success=success,
        returncode=proc.returncode,
        stdout=(proc.stdout or "")[-4000:],
        stderr=(proc.stderr or "")[-4000:],
        error=error,
    )


def deploy(game: Game, session: Session) -> DeployReport:
    """Compose pre_flight_check → plan_deploy → execute_plan → redmod_deploy.

    If pre-flight fails, returns an empty report with the ``preflight`` field
    populated so callers can surface the reason. On a clean execute (no failures
    and no preflight refusal), marks all enabled mods as deployed and clears any
    pending drift flag. If any enabled mod has REDmod content, also invokes
    ``redMod.exe deploy`` so the compiled cache stays in sync with the deployed
    junctions; the redmod result is attached to ``report.redmod`` regardless of
    outcome.
    """
    pre = pre_flight_check(game)
    if not pre.ok:
        return DeployReport(total=0, done=0, failed=0, results=[], preflight=pre)
    plan, skipped = plan_deploy(game, session)
    report = execute_plan(plan, session)
    report.skipped_existing = skipped
    if report.is_clean:
        mods = session.exec(
            select(InstalledMod).where(
                InstalledMod.game_id == game.id,
                InstalledMod.disabled.is_(False),  # type: ignore[union-attr]
            )
        ).all()
        for m in mods:
            m.deployed = True
            m.deploy_drift = False
            session.add(m)
        session.commit()
        if _has_enabled_redmods(game, session):
            report.redmod = redmod_deploy(game)
    return report


def replay_pending_journal(game: Game, session: Session) -> None:
    """Roll back any journal entries left in 'pending' state from a prior interrupted deploy.

    For each pending entry, attempts to undo the operation (unlink for 'link', remove_junction
    for 'junction') so the filesystem is left consistent.  The entry is then marked 'failed'
    regardless of whether the undo succeeded, because the original operation never completed.
    Errors during rollback are logged as warnings — they do not raise so that startup continues.
    """
    pending = session.exec(
        select(DeployJournalEntry).where(
            DeployJournalEntry.game_id == game.id,
            DeployJournalEntry.status == "pending",
        )
    ).all()
    for entry in pending:
        try:
            if entry.operation == "link":
                unlink(Path(entry.dst))
            elif entry.operation == "junction":
                remove_junction(Path(entry.dst))
        except VfsError as exc:
            logger.warning("journal replay rollback failed for %s: %s", entry.dst, exc)
        entry.status = "failed"
        entry.error = entry.error or "rolled back by journal replay"
        session.add(entry)
    session.commit()
