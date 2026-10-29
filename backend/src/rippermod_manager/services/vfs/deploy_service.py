"""Orchestrates VFS deployment: planning, journaling, execution."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import (  # noqa: F401 used in plan_deploy
    DeployJournalEntry,
    DisplacedFile,
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
from rippermod_manager.services.paths import get_mods_dir
from rippermod_manager.services.save_backup_service import maybe_backup_before
from rippermod_manager.services.vfs.ownership import owners_by_key, path_key, winner_map
from rippermod_manager.services.vfs.primitives import (
    AlreadyExistsError,
    VfsError,
    hardlink,
    is_game_running,
    junction,
    junction_points_into,
    probe_hardlink_support,
    remove_junction,
    same_volume,
    unlink,
    verify_link,
)

logger = logging.getLogger(__name__)

GAME_EXE = "Cyberpunk2077.exe"
REDMOD_REL_PATH = Path("tools") / "redmod" / "bin" / "redMod.exe"
# Foreign files that force deploy moves aside live under <mods_dir>/_displaced/:
# same volume as staging, so the move is an atomic rename.
DISPLACED_DIRNAME = "_displaced"
REDMOD_TIMEOUT_S = 600  # generous: heavy REDmod sets can take several minutes to compile


def pre_flight_check(game: Game) -> PreflightReport:
    report = PreflightReport()
    install = Path(game.install_path)
    staging = get_mods_dir(game)
    staging.mkdir(parents=True, exist_ok=True)

    if is_game_running(GAME_EXE):
        report.ok = False
        report.game_running = True
        report.reasons.append("Cyberpunk 2077 is running, close it before deploying.")

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


def _redmod_root(relative_path: str) -> str | None:
    """``<name>`` for a file under ``mods/<name>/...``, else None."""
    parts = relative_path.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0] == "mods":
        return parts[1]
    return None


def plan_deploy(
    game: Game, session: Session, *, paths: set[str] | None = None
) -> tuple[DeployPlan, int]:
    """Build a DeployPlan that links the winner of every destination path (S4).

    For each ownership key (``ownership.path_key``) only the enabled owner with
    the highest ``win_seq`` is linked: one ``link`` per hardlinked file, one
    ``junction`` per REDmod ``mods/<name>`` root. When the destination is
    currently the hardlink of another owner of the same key, an ``unlink``
    (carrying that owner's staged source, so execution can verify it) runs
    before the ``link``. ``paths`` restricts the plan to those keys.

    Ops whose destination already matches the winner's staged source are
    skipped (idempotent re-deploy); the count of skipped ops is returned
    alongside the plan so callers can surface "already up to date".
    """
    install = Path(game.install_path)
    staging_root = get_mods_dir(game)

    plan = DeployPlan(game_id=game.id)
    skipped_existing = 0
    owners = owners_by_key(session, game.id)  # type: ignore[arg-type]

    for key, (mod, f) in winner_map(session, game.id).items():  # type: ignore[arg-type]
        if paths is not None and key not in paths:
            continue
        redmod_name = _redmod_root(f.relative_path) if f.link_kind == "junction" else None
        if redmod_name is not None:
            redmod_dst = install / "mods" / redmod_name
            redmod_src = staging_root / mod.staging_dir / "mods" / redmod_name
            # Hand the junction over when it points into another owner's staging
            # (Overwrite between two REDmods with the same mods/<name>).
            previous = next(
                (
                    (other.id, staging_root / other.staging_dir / "mods" / redmod_name)
                    for other, other_f in owners.get(key, [])
                    if other.id != mod.id
                    and other_f.link_kind == "junction"
                    and junction_points_into(
                        redmod_dst, staging_root / other.staging_dir / "mods" / redmod_name
                    )
                ),
                None,
            )
            if previous is not None:
                previous_id, previous_root = previous
                plan.ops.append(
                    DeployOp(
                        operation="rm_junction",
                        src=str(previous_root),
                        dst=str(redmod_dst),
                        installed_mod_id=previous_id,
                        relative_path=f"mods/{redmod_name}",
                    )
                )
            elif redmod_dst.is_dir():
                # Idempotency: the winner's junction, or a folder no owner claims,
                # is already there; presence is treated as ours, as before.
                skipped_existing += 1
                continue
            plan.ops.append(
                DeployOp(
                    operation="junction",
                    src=str(redmod_src),
                    dst=str(redmod_dst),
                    installed_mod_id=mod.id,
                    relative_path=f"mods/{redmod_name}",
                )
            )
            continue

        rel = f.relative_path.replace("\\", "/")
        src = staging_root / mod.staging_dir / f.source_path.replace("\\", "/")
        dst = install / rel
        # Idempotency: hardlink already points to the winner's staged source.
        if verify_link(src, dst):
            skipped_existing += 1
            continue
        # Hand the path over: drop the link of the owner that held it before.
        for other_mod, other_f in owners.get(key, []):
            if other_mod.id == mod.id or other_f.link_kind == "junction":
                continue
            other_src = (
                staging_root / other_mod.staging_dir / other_f.source_path.replace("\\", "/")
            )
            if verify_link(other_src, dst):
                plan.ops.append(
                    DeployOp(
                        operation="unlink",
                        src=str(other_src),
                        dst=str(dst),
                        installed_mod_id=other_mod.id,
                        relative_path=rel,
                    )
                )
                break
        plan.ops.append(
            DeployOp(
                operation="link",
                src=str(src),
                dst=str(dst),
                installed_mod_id=mod.id,
                relative_path=rel,
            )
        )

    return plan, skipped_existing


def relink_paths(game: Game, session: Session, paths: set[str]) -> DeployReport:
    """Link the current winner of each key in *paths* (no redMod compile).

    Used right after a mod gives paths up (uninstall, disable) so the next
    owner takes them over in the same operation, and on enable.
    """
    if not paths:
        return DeployReport(total=0, done=0, failed=0)
    pre = pre_flight_check(game)
    if not pre.ok:
        return DeployReport(total=0, done=0, failed=0, results=[], preflight=pre)
    plan, skipped = plan_deploy(game, session, paths=paths)
    report = execute_plan(plan, session)
    report.skipped_existing = skipped
    return report


def paths_not_relinked(
    game: Game, session: Session, paths: set[str], report: DeployReport
) -> list[str]:
    """Relative paths ``relink_paths`` should have linked but did not.

    When pre-flight refused (e.g. the game is running) that is every path the
    plan would link; otherwise it is the link/junction ops that failed.
    """
    if report.preflight is not None and not report.preflight.ok:
        plan, _skipped = plan_deploy(game, session, paths=paths)
        pending = {op.relative_path for op in plan.ops if op.operation in ("link", "junction")}
    else:
        pending = {
            r.op.relative_path
            for r in report.results
            if r.status == "failed" and r.op.operation in ("link", "junction")
        }
    return sorted(pending)


def execute_plan(
    plan: DeployPlan,
    session: Session,
    *,
    force: bool = False,
    displaced_root: Path | None = None,
) -> DeployReport:
    """Run each op in `plan`, persisting a write-ahead journal entry before each
    filesystem mutation so crash recovery can roll back partial state on next start.

    When ``force=True`` and a link/junction op hits ``AlreadyExistsError`` (a foreign
    file is squatting on the destination), the foreign entry is moved to
    ``displaced_root / op.relative_path`` (journaled as ``displace`` and recorded
    in ``displaced_files``) and the op is retried once (S6). Nothing is ever
    deleted: without ``displaced_root``, or when a backup already sits at that
    path, the op fails and the foreign entry stays. Without ``force``, such
    conflicts surface as failures so the user can decide whether to overwrite.
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
            elif op.operation in ("unlink", "rm_junction"):
                if not _remove_own_link(op):
                    # S5: not this mod's link (vanilla file, another tool's copy,
                    # another mod's junction). Leave it and keep going.
                    entry.status = "done"
                    entry.error = "left in place: destination is not this mod's link"
                    session.add(entry)
                    results.append(DeployOpResult(op=op, status="foreign"))
                    continue
            elif op.operation == "junction":
                junction(Path(op.src), Path(op.dst))
            else:
                raise VfsError(f"unknown op: {op.operation}")
            entry.status = "done"
            results.append(DeployOpResult(op=op, status="done"))
        except AlreadyExistsError as exc:
            if force and op.operation in ("link", "junction"):
                try:
                    row = _displace(op, plan.game_id, session, displaced_root)
                    try:
                        if op.operation == "link":
                            hardlink(Path(op.src), Path(op.dst))
                        else:
                            junction(Path(op.src), Path(op.dst))
                    except (VfsError, OSError):
                        _undo_displace(row, Path(op.dst), session)
                        raise
                    entry.status = "done"
                    results.append(DeployOpResult(op=op, status="done"))
                except (VfsError, OSError) as retry_exc:
                    msg = f"force overwrite failed: {retry_exc}"
                    entry.status = "failed"
                    entry.error = msg
                    results.append(DeployOpResult(op=op, status="failed", error=msg))
            else:
                entry.status = "failed"
                entry.error = str(exc)
                results.append(DeployOpResult(op=op, status="failed", error=str(exc)))
        except VfsError as exc:
            entry.status = "failed"
            entry.error = str(exc)
            results.append(DeployOpResult(op=op, status="failed", error=str(exc)))

        session.add(entry)

    session.commit()
    done = sum(1 for r in results if r.status == "done")
    failed = sum(1 for r in results if r.status == "failed")
    foreign = sum(1 for r in results if r.status == "foreign")
    return DeployReport(
        total=len(results), done=done, failed=failed, foreign=foreign, results=results
    )


def _remove_own_link(op: DeployOp) -> bool:
    """Remove ``op.dst`` only if it is the link of ``op.src`` (S5).

    Returns True when the destination is gone afterwards (removed, or already
    absent), False when it is someone else's and was left untouched. An
    ``unlink`` needs ``op.dst`` to be a hardlink of ``op.src``; an
    ``rm_junction`` needs it to be a junction pointing inside ``op.src``.
    """
    dst = Path(op.dst)
    if not dst.exists() and not dst.is_symlink():
        return True
    if not op.src:
        return False
    if op.operation == "unlink":
        if not verify_link(Path(op.src), dst):
            return False
        unlink(dst)
        return True
    if not junction_points_into(dst, Path(op.src)):
        return False
    remove_junction(dst)
    return True


def _displace(
    op: DeployOp, game_id: int, session: Session, displaced_root: Path | None
) -> DisplacedFile:
    """Move the foreign entry at ``op.dst`` to the displaced area (S6).

    Write-ahead: the ``displace`` journal entry and the ``displaced_files`` row
    are committed before the move, so a crash in between is rolled forward on
    startup. Raises ``VfsError`` (nothing moved) when there is nowhere safe to
    put it.
    """
    if displaced_root is None:
        raise VfsError(f"destination exists and no displaced area was given: {op.dst}")
    if not op.relative_path:
        raise VfsError(f"cannot displace {op.dst}: the op has no relative path")
    backup = displaced_root / op.relative_path
    if backup.exists() or backup.is_symlink():
        raise VfsError(f"a displaced copy already exists at {backup}")
    entry = DeployJournalEntry(
        game_id=game_id, operation="displace", src=op.dst, dst=str(backup), status="pending"
    )
    row = DisplacedFile(
        game_id=game_id,
        relative_path=op.relative_path,
        backup_path=str(backup),
        occupant_mod_id=op.installed_mod_id,
    )
    session.add(entry)
    session.add(row)
    session.commit()
    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        os.replace(op.dst, backup)
    except OSError as exc:
        entry.status = "failed"
        entry.error = str(exc)
        session.add(entry)
        session.delete(row)
        session.commit()
        raise VfsError(f"could not move {op.dst} aside: {exc}") from exc
    entry.status = "done"
    session.add(entry)
    session.commit()
    return row


def _undo_displace(row: DisplacedFile, original: Path, session: Session) -> None:
    """Put a just-displaced entry back after its replacement link failed."""
    try:
        if not original.exists() and not original.is_symlink():
            os.replace(row.backup_path, original)
            session.delete(row)
            session.commit()
    except OSError:
        logger.exception("Could not put %s back after a failed link", original)


def displaced_root_for(game: Game) -> Path:
    return get_mods_dir(game) / DISPLACED_DIRNAME


def restore_displaced(
    game: Game, session: Session, *, occupant_mod_id: int | None = None
) -> list[str]:
    """Put displaced files back where they were (S6).

    Restores every row of the game, or only those whose occupant is
    ``occupant_mod_id``. A row whose original path is occupied again is left
    alone (file in ``_displaced``, row kept) and its relative path returned.
    Call it after the occupant's own links are gone.
    """
    query = select(DisplacedFile).where(DisplacedFile.game_id == game.id)
    if occupant_mod_id is not None:
        query = query.where(DisplacedFile.occupant_mod_id == occupant_mod_id)
    install = Path(game.install_path)
    not_restored: list[str] = []
    for row in session.exec(query).all():
        original = install / row.relative_path
        backup = Path(row.backup_path)
        if not backup.exists() and not backup.is_symlink():
            logger.warning("Displaced backup vanished, dropping its record: %s", backup)
            session.delete(row)
            continue
        if original.exists() or original.is_symlink():
            not_restored.append(row.relative_path)
            continue
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            os.replace(backup, original)
        except OSError as exc:
            logger.warning("Could not restore displaced %s: %s", row.relative_path, exc)
            not_restored.append(row.relative_path)
            continue
        session.delete(row)
    session.commit()
    return not_restored


def plan_remove_mod_links(game: Game, mod: InstalledMod, session: Session) -> DeployPlan:
    """Plan the removal of *mod*'s own game-dir links.

    One ``unlink`` per hardlinked file and one ``rm_junction`` per REDmod
    root, each carrying the mod's staged source so ``execute_plan`` can check
    the destination really is this mod's link. Paths currently linked to
    another owner of the same key are left out: they are that owner's.
    """
    install = Path(game.install_path)
    staging_root = get_mods_dir(game)
    owners = owners_by_key(session, game.id)  # type: ignore[arg-type]
    plan = DeployPlan(game_id=game.id)  # type: ignore[arg-type]
    seen_roots: set[str] = set()
    _ = mod.files
    for f in mod.files:
        key = path_key(f.relative_path, f.link_kind)
        others = [(m, of) for m, of in owners.get(key, []) if m.id != mod.id]
        redmod_name = _redmod_root(f.relative_path) if f.link_kind == "junction" else None
        if redmod_name is not None:
            if key in seen_roots:
                continue
            seen_roots.add(key)
            dst = install / "mods" / redmod_name
            src = staging_root / mod.staging_dir / "mods" / redmod_name
            if any(
                junction_points_into(dst, staging_root / m.staging_dir / "mods" / redmod_name)
                for m, _of in others
            ):
                continue
            plan.ops.append(
                DeployOp(
                    operation="rm_junction",
                    src=str(src),
                    dst=str(dst),
                    installed_mod_id=mod.id,
                    relative_path=f"mods/{redmod_name}",
                )
            )
            continue
        rel = f.relative_path.replace("\\", "/")
        dst = install / rel
        src = staging_root / mod.staging_dir / f.source_path.replace("\\", "/")
        if any(
            verify_link(staging_root / m.staging_dir / of.source_path.replace("\\", "/"), dst)
            for m, of in others
            if of.link_kind != "junction"
        ):
            continue
        plan.ops.append(
            DeployOp(
                operation="unlink",
                src=str(src),
                dst=str(dst),
                installed_mod_id=mod.id,
                relative_path=rel,
            )
        )
    return plan


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
            reasons=["Cyberpunk 2077 is running, close it before undeploying."],
        )
        return DeployReport(total=0, done=0, failed=0, results=[], preflight=refuse_pre)

    maybe_backup_before(game, session, reason="pre-undeploy")

    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.deployed.is_(True),  # type: ignore[union-attr]
        )
    ).all()

    ops: list[DeployOp] = []
    for mod in mods:
        ops.extend(plan_remove_mod_links(game, mod, session).ops)

    plan = DeployPlan(game_id=game.id, ops=ops)
    report = execute_plan(plan, session)
    # With our links gone, everything force deploy moved aside goes back (S6).
    report.displaced_not_restored = restore_displaced(game, session)

    if report.is_clean:
        for m in mods:
            m.deployed = False
            session.add(m)
        session.commit()
    return report


def detect_drift(game: Game, session: Session) -> DriftReport:
    install = Path(game.install_path)
    staging_root = get_mods_dir(game)

    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.disabled.is_(False),  # type: ignore[union-attr]
        )
    ).all()

    total = linked = missing = foreign = 0
    by_mod: dict[int, dict[str, int]] = {}
    # A path another mod wins is that mod's to link (S4): not drift for this one (S6).
    winners = winner_map(session, game.id)  # type: ignore[arg-type]

    for mod in mods:
        _ = mod.files
        m_linked = m_missing = m_foreign = 0
        # Cache per-junction-root checks so we don't probe the same reparse point N times
        # for an N-file REDmod and so all files under the same root agree on linked/missing.
        junction_root_state: dict[Path, bool] = {}
        for f in mod.files:
            winner = winners.get(path_key(f.relative_path, f.link_kind))
            if winner is not None and winner[0].id != mod.id:
                continue
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


def preview_displacements(game: Game, session: Session) -> list[str]:
    """Relative paths a force deploy would move aside, without touching disk (S6).

    These are the ``link``/``junction`` ops of the current plan whose
    destination exists and is not freed by an ``unlink`` earlier in the plan
    (a path handed over between owners is not foreign).
    """
    plan, _skipped = plan_deploy(game, session)
    freed: set[str] = set()
    paths: list[str] = []
    for op in plan.ops:
        if op.operation in ("unlink", "rm_junction"):
            freed.add(op.dst)
            continue
        if op.operation not in ("link", "junction") or op.dst in freed:
            continue
        dst = Path(op.dst)
        if dst.exists() or dst.is_symlink():
            paths.append(op.relative_path)
    return paths


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


def deploy(game: Game, session: Session, *, force: bool = False) -> DeployReport:
    """Compose pre_flight_check, plan_deploy, execute_plan and redmod_deploy.

    If pre-flight fails, returns an empty report with the ``preflight`` field
    populated so callers can surface the reason. On a clean execute (no failures
    and no preflight refusal), marks all enabled mods as deployed and clears any
    pending drift flag. If any enabled mod has REDmod content, also invokes
    ``redMod.exe deploy`` so the compiled cache stays in sync with the deployed
    junctions; the redmod result is attached to ``report.redmod`` regardless of
    outcome.

    ``force=True`` makes ``execute_plan`` overwrite foreign files squatting on a
    destination instead of skipping them as conflicts. Use this when the user
    has explicitly opted into a "force redeploy" (e.g., to migrate from another
    mod manager that left copy-installed files behind).
    """
    pre = pre_flight_check(game)
    if not pre.ok:
        return DeployReport(total=0, done=0, failed=0, results=[], preflight=pre)
    maybe_backup_before(game, session, reason="pre-deploy")
    plan, skipped = plan_deploy(game, session)
    report = execute_plan(
        plan, session, force=force, displaced_root=displaced_root_for(game) if force else None
    )
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
    for 'junction') so the filesystem is left consistent, but only when the destination is
    that entry's own link (S5): anything else at the path is left untouched. The entry is
    then marked 'failed' regardless of whether the undo succeeded, because the original
    operation never completed.
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
            if entry.operation == "adopt":
                # Roll FORWARD: the moved bytes are safe in staging (src). If the
                # game-dir hardlink (dst) never got created, recreate it so the
                # game file is not left missing. Never delete the staging copy.
                src = Path(entry.src)
                dst = Path(entry.dst)
                if src.exists() and not dst.exists():
                    hardlink(src, dst)
                entry.status = "done"
                entry.error = entry.error or "rolled forward by journal replay"
                session.add(entry)
                continue
            # Undo only what this entry created (S5): a destination that is not
            # the link of entry.src (e.g. a vanilla file) is left alone.
            if entry.operation == "displace":
                # Roll FORWARD: the displaced_files row was committed with this
                # entry, so finish the move (src = original, dst = backup).
                src, dst = Path(entry.src), Path(entry.dst)
                if (src.exists() or src.is_symlink()) and not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(src, dst)
                entry.status = "done"
                entry.error = entry.error or "rolled forward by journal replay"
                session.add(entry)
                continue
            src, dst = Path(entry.src), Path(entry.dst)
            if entry.operation == "link" and verify_link(src, dst):
                unlink(dst)
            elif entry.operation == "junction" and junction_points_into(dst, src):
                remove_junction(dst)
        except (VfsError, OSError) as exc:
            logger.warning("journal replay rollback failed for %s: %s", entry.dst, exc)
        entry.status = "failed"
        entry.error = entry.error or "rolled back by journal replay"
        session.add(entry)
    session.commit()
