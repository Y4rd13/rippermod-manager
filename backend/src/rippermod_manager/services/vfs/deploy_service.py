"""Orchestrates VFS deployment: planning, journaling, execution."""

from __future__ import annotations

import logging
import shutil
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
    except Exception as exc:  # file I/O can raise many OSError subclasses
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
    except Exception as exc:  # probe touches filesystem; wide catch intentional
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


def plan_deploy(game: Game, session: Session) -> DeployPlan:
    """Build a DeployPlan from the installed-mod manifest for a game.

    Enumerates all enabled InstalledMod rows and their InstalledModFile rows,
    producing one DeployOp per file (link) or per REDmod subtree root (junction).
    Junction ops are deduplicated: only one junction per mods/<name> directory.
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
                    plan.ops.append(
                        DeployOp(
                            operation="junction",
                            src=str(redmod_src),
                            dst=str(redmod_dst),
                            installed_mod_id=mod.id,
                        )
                    )
                    continue
            plan.ops.append(
                DeployOp(
                    operation="link",
                    src=str(src),
                    dst=str(dst),
                    installed_mod_id=mod.id,
                )
            )

    return plan


def execute_plan(plan: DeployPlan, session: Session) -> DeployReport:
    results: list[DeployOpResult] = []

    for op in plan.ops:
        entry = DeployJournalEntry(
            game_id=plan.game_id,
            operation=op.operation,
            src=op.src,
            dst=op.dst,
            status="pending",
        )
        session.add(entry)
        session.flush()

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

    Only checks ``game_running`` from pre-flight — filesystem support gates are
    irrelevant when removing files rather than creating them.  Marks
    ``deployed=False`` only when the execute step completes without failures.
    """
    pre = pre_flight_check(game)
    if pre.game_running:
        return DeployReport(total=0, done=0, failed=0, results=[])

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
        for f in mod.files:
            total += 1
            src = staging_root / mod.staging_dir / f.source_path.replace("\\", "/")
            dst = install / f.relative_path.replace("\\", "/")
            if not dst.exists():
                missing += 1
                m_missing += 1
                continue
            if f.link_kind == "hardlink":
                if verify_link(src, dst):
                    linked += 1
                    m_linked += 1
                else:
                    foreign += 1
                    m_foreign += 1
            elif f.link_kind == "junction":
                if dst.is_dir():
                    linked += 1
                    m_linked += 1
                else:
                    missing += 1
                    m_missing += 1
        if mod.id is not None:
            by_mod[mod.id] = {"linked": m_linked, "missing": m_missing, "foreign": m_foreign}

    return DriftReport(total=total, linked=linked, missing=missing, foreign=foreign, by_mod=by_mod)


def deploy(game: Game, session: Session) -> DeployReport:
    """Compose pre_flight_check → plan_deploy → execute_plan.

    If pre-flight fails, returns an empty report without touching the DB.
    On a clean execute (no failures), marks all enabled mods as deployed and
    clears any pending drift flag.
    """
    pre = pre_flight_check(game)
    if not pre.ok:
        return DeployReport(total=0, done=0, failed=0, results=[])
    plan = plan_deploy(game, session)
    report = execute_plan(plan, session)
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
    return report
