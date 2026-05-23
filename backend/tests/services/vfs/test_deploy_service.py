import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import DeployJournalEntry, InstalledMod, InstalledModFile
from rippermod_manager.schemas.deploy import DeployOp, DeployPlan
from rippermod_manager.services.vfs.deploy_service import (
    REDMOD_REL_PATH,
    deploy,
    detect_drift,
    execute_plan,
    plan_deploy,
    pre_flight_check,
    redmod_deploy,
    replay_pending_journal,
    undeploy,
)


def _stage_redmod_binary(game: Game) -> Path:
    """Create a stub redMod.exe so _redmod_exe() finds it. Caller mocks subprocess."""
    exe = Path(game.install_path) / REDMOD_REL_PATH
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("stub")
    return exe


def _make_redmod_proc(returncode: int = 0, stdout: str = "ok", stderr: str = "") -> MagicMock:
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def make_game(tmp_path: Path) -> Game:
    install = tmp_path / "game"
    (install / "downloaded_mods").mkdir(parents=True)
    return Game(id=1, name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(install))


def test_pre_flight_clean(tmp_path):
    g = make_game(tmp_path)
    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        r = pre_flight_check(g)
    assert r.ok is True
    assert r.game_running is False


def test_pre_flight_refuses_if_game_running(tmp_path):
    g = make_game(tmp_path)
    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=True):
        r = pre_flight_check(g)
    assert r.ok is False
    assert r.game_running is True
    assert any("running" in s.lower() for s in r.reasons)


def test_plan_includes_hardlink_for_each_file(in_memory_session, sample_game):
    session: Session = in_memory_session
    game = sample_game
    mod = InstalledMod(
        game_id=game.id,
        name="TestMod",
        staging_dir="TestMod",
        disabled=False,
        deployed=False,
    )
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="r6/scripts/foo.reds",
            source_path="r6/scripts/foo.reds",
            link_kind="hardlink",
        )
    )
    session.commit()

    plan, skipped = plan_deploy(game, session)

    assert skipped == 0
    assert len(plan.ops) == 1
    assert plan.ops[0].operation == "link"
    assert plan.ops[0].src.endswith("downloaded_mods/TestMod/r6/scripts/foo.reds") or plan.ops[
        0
    ].src.endswith("downloaded_mods\\TestMod\\r6\\scripts\\foo.reds")
    assert plan.ops[0].dst.endswith("r6/scripts/foo.reds") or plan.ops[0].dst.endswith(
        "r6\\scripts\\foo.reds"
    )


def test_plan_skips_disabled_mods(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    mod = InstalledMod(game_id=game.id, name="Off", staging_dir="Off", disabled=True)
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="a", source_path="a"))
    session.commit()

    plan, skipped = plan_deploy(game, session)
    assert plan.is_empty
    assert skipped == 0


def test_plan_uses_junction_for_redmod_subtrees(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    mod = InstalledMod(game_id=game.id, name="MyREDmod", staging_dir="MyREDmod")
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="mods/MyREDmod/info.json",
            source_path="mods/MyREDmod/info.json",
            link_kind="junction",
        )
    )
    session.commit()

    plan, skipped = plan_deploy(game, session)
    junction_ops = [op for op in plan.ops if op.operation == "junction"]
    assert skipped == 0
    assert len(junction_ops) == 1
    assert junction_ops[0].dst.endswith("mods/MyREDmod") or junction_ops[0].dst.endswith(
        "mods\\MyREDmod"
    )


def test_execute_plan_creates_hardlinks_and_journals(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "TestMod" / "r6" / "scripts"
    staging.mkdir(parents=True)
    src = staging / "foo.reds"
    src.write_text("// test")

    plan = DeployPlan(
        game_id=game.id,
        ops=[
            DeployOp(
                operation="link",
                src=str(src),
                dst=str(Path(game.install_path) / "r6" / "scripts" / "foo.reds"),
                installed_mod_id=1,
            ),
        ],
    )

    report = execute_plan(plan, session)

    assert report.failed == 0
    assert report.done == 1
    dst = Path(game.install_path) / "r6" / "scripts" / "foo.reds"
    assert dst.exists()
    journal = session.exec(
        select(DeployJournalEntry).where(DeployJournalEntry.game_id == game.id)
    ).all()
    assert all(j.status == "done" for j in journal)


def test_execute_plan_force_overwrites_foreign_file(in_memory_session, sample_game):
    """A regular file squatting on the destination is overwritten when force=True."""
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "TestMod" / "r6" / "scripts"
    staging.mkdir(parents=True)
    src = staging / "foo.reds"
    src.write_text("staged content")

    dst = Path(game.install_path) / "r6" / "scripts" / "foo.reds"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("foreign content from another mod manager")

    plan = DeployPlan(
        game_id=game.id,
        ops=[
            DeployOp(
                operation="link",
                src=str(src),
                dst=str(dst),
                installed_mod_id=1,
            ),
        ],
    )

    report = execute_plan(plan, session, force=True)

    assert report.failed == 0
    assert report.done == 1
    # Destination is now a hardlink to the staged source: identical content.
    assert dst.read_text() == "staged content"
    # And shares an inode with src.
    assert dst.stat().st_ino == src.stat().st_ino


def test_execute_plan_without_force_keeps_foreign_and_fails(
    in_memory_session,
    sample_game,
):
    """Without force, an op pointing at an occupied dst fails with destination exists."""
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "TestMod" / "r6" / "scripts"
    staging.mkdir(parents=True)
    src = staging / "foo.reds"
    src.write_text("staged content")

    dst = Path(game.install_path) / "r6" / "scripts" / "foo.reds"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("foreign content")

    plan = DeployPlan(
        game_id=game.id,
        ops=[
            DeployOp(
                operation="link",
                src=str(src),
                dst=str(dst),
                installed_mod_id=1,
            ),
        ],
    )

    report = execute_plan(plan, session)

    assert report.failed == 1
    assert report.done == 0
    # Foreign file is untouched.
    assert dst.read_text() == "foreign content"
    assert "destination exists" in report.results[0].error


def test_execute_plan_failure_marks_journal_failed(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    plan = DeployPlan(
        game_id=game.id,
        ops=[
            DeployOp(
                operation="link",
                src="/does/not/exist.txt",
                dst=str(Path(game.install_path) / "r6" / "scripts" / "ghost.reds"),
                installed_mod_id=1,
            ),
        ],
    )

    report = execute_plan(plan, session)

    assert report.failed == 1
    journal = session.exec(
        select(DeployJournalEntry).where(DeployJournalEntry.status == "failed")
    ).all()
    assert len(journal) == 1


def test_deploy_full_round_trip(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game

    staging = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging.mkdir(parents=True)
    (staging / "a.reds").write_text("// a")

    mod = InstalledMod(
        game_id=game.id, name="Demo", staging_dir="Demo", disabled=False, deployed=False
    )
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="r6/scripts/a.reds",
            source_path="r6/scripts/a.reds",
            link_kind="hardlink",
        )
    )
    session.commit()

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        report = deploy(game, session)

    assert report.failed == 0
    session.refresh(mod)
    assert mod.deployed is True


def test_undeploy_removes_links_keeps_staging(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    staging_root = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging_root.mkdir(parents=True)
    (staging_root / "a.reds").write_text("// a")
    dst_dir = Path(game.install_path) / "r6" / "scripts"
    dst_dir.mkdir(parents=True)
    os.link(staging_root / "a.reds", dst_dir / "a.reds")

    mod = InstalledMod(game_id=game.id, name="Demo", staging_dir="Demo", deployed=True)
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="r6/scripts/a.reds",
            source_path="r6/scripts/a.reds",
        )
    )
    session.commit()

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        undeploy(game, session)

    assert not (dst_dir / "a.reds").exists()
    assert (staging_root / "a.reds").exists()
    session.refresh(mod)
    assert mod.deployed is False


def test_drift_clean_after_deploy(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging.mkdir(parents=True)
    (staging / "a.reds").write_text("// a")

    mod = InstalledMod(game_id=game.id, name="Demo", staging_dir="Demo")
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="r6/scripts/a.reds",
            source_path="r6/scripts/a.reds",
        )
    )
    session.commit()

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        deploy(game, session)

    drift = detect_drift(game, session)
    assert drift.is_clean
    assert drift.linked == 1
    assert drift.missing == 0


def test_drift_counts_redmod_files_under_existing_junction_as_linked(
    in_memory_session, sample_game
):
    """REDmod files share one junction at mods/<name>/.  detect_drift used to call
    is_dir() on each per-file path (info.json, scripts/x.script), which returns False
    for actual files inside the reparse point — so a healthy REDmod was reported as
    fully missing.  Verify all per-file records under an existing junction root count
    as linked.
    """
    session = in_memory_session
    game = sample_game

    # Simulate the deployed state: the junction root exists as a real dir.
    (Path(game.install_path) / "mods" / "MyREDmod").mkdir(parents=True)

    mod = InstalledMod(game_id=game.id, name="MyREDmod", staging_dir="MyREDmod", deployed=True)
    session.add(mod)
    session.flush()
    # Three per-file InstalledModFile records that all live under one junction root.
    for rel in (
        "mods/MyREDmod/info.json",
        "mods/MyREDmod/scripts/a.script",
        "mods/MyREDmod/scripts/sub/b.script",
    ):
        session.add(
            InstalledModFile(
                installed_mod_id=mod.id,
                relative_path=rel,
                source_path=rel,
                link_kind="junction",
            )
        )
    session.commit()

    drift = detect_drift(game, session)

    assert drift.total == 3
    assert drift.linked == 3
    assert drift.missing == 0
    assert drift.foreign == 0


def test_drift_counts_redmod_files_as_missing_when_junction_root_absent(
    in_memory_session, sample_game
):
    """Mirror of the above: when the junction root is gone, every per-file record
    under it counts as missing (and we only probe the root once, not per file).
    """
    session = in_memory_session
    game = sample_game

    mod = InstalledMod(game_id=game.id, name="MissingMod", staging_dir="MissingMod", deployed=True)
    session.add(mod)
    session.flush()
    for rel in (
        "mods/MissingMod/info.json",
        "mods/MissingMod/scripts/a.script",
    ):
        session.add(
            InstalledModFile(
                installed_mod_id=mod.id,
                relative_path=rel,
                source_path=rel,
                link_kind="junction",
            )
        )
    session.commit()

    drift = detect_drift(game, session)

    assert drift.total == 2
    assert drift.missing == 2
    assert drift.linked == 0


def test_drift_detects_missing_link(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging.mkdir(parents=True)
    (staging / "a.reds").write_text("// a")

    mod = InstalledMod(game_id=game.id, name="Demo", staging_dir="Demo", deployed=True)
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="r6/scripts/a.reds",
            source_path="r6/scripts/a.reds",
        )
    )
    session.commit()

    drift = detect_drift(game, session)
    assert drift.missing == 1
    assert drift.linked == 0


def test_replay_clears_pending_entries(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    session.add(
        DeployJournalEntry(
            game_id=game.id,
            operation="link",
            src="/nope",
            dst=str(Path(game.install_path) / "r6" / "scripts" / "ghost.reds"),
            status="pending",
        )
    )
    session.commit()

    replay_pending_journal(game, session)

    pending = session.exec(
        select(DeployJournalEntry).where(DeployJournalEntry.status == "pending")
    ).all()
    assert len(pending) == 0


def test_plan_skips_files_already_correctly_linked(in_memory_session, sample_game):
    """Re-running plan_deploy after a successful deploy should produce an empty plan."""
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging.mkdir(parents=True)
    (staging / "a.reds").write_text("// a")

    mod = InstalledMod(game_id=game.id, name="Demo", staging_dir="Demo", disabled=False)
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="r6/scripts/a.reds",
            source_path="r6/scripts/a.reds",
            link_kind="hardlink",
        )
    )
    session.commit()

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        first = deploy(game, session)
        second = deploy(game, session)

    assert first.failed == 0
    assert first.done == 1
    assert second.failed == 0
    assert second.total == 0  # nothing to do — all already linked
    assert second.skipped_existing == 1


def test_deploy_surfaces_preflight_when_game_running(in_memory_session, sample_game):
    """When the game is running, deploy() should return a report with preflight reasons."""
    session = in_memory_session
    game = sample_game

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=True):
        report = deploy(game, session)

    assert report.total == 0
    assert report.preflight is not None
    assert report.preflight.ok is False
    assert report.preflight.game_running is True
    assert any("running" in r.lower() for r in report.preflight.reasons)
    assert report.is_clean is False  # preflight refusal counts as not-clean


def test_undeploy_surfaces_preflight_when_game_running(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=True):
        report = undeploy(game, session)

    assert report.preflight is not None
    assert report.preflight.game_running is True


def test_undeploy_triggers_save_backup(in_memory_session, sample_game, monkeypatch):
    """undeploy takes a pre-undeploy save snapshot once past the game-running gate."""
    session = in_memory_session
    game = sample_game
    calls: list[str] = []
    monkeypatch.setattr(
        "rippermod_manager.services.vfs.deploy_service.maybe_backup_before",
        lambda g, s, *, reason: calls.append(reason),
    )
    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        undeploy(game, session)
    assert calls == ["pre-undeploy"]


def test_undeploy_refused_skips_save_backup(in_memory_session, sample_game, monkeypatch):
    """A refused undeploy (game running) must not snapshot — the hook is after the gate."""
    session = in_memory_session
    game = sample_game
    calls: list[str] = []
    monkeypatch.setattr(
        "rippermod_manager.services.vfs.deploy_service.maybe_backup_before",
        lambda g, s, *, reason: calls.append(reason),
    )
    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=True):
        undeploy(game, session)
    assert calls == []


def test_plan_skips_junction_when_dir_already_exists(in_memory_session, sample_game):
    """If a junction's destination dir already exists, plan_deploy treats it as up-to-date."""
    session = in_memory_session
    game = sample_game

    # Pre-create the destination dir to simulate an existing junction.
    (Path(game.install_path) / "mods" / "MyREDmod").mkdir(parents=True)

    mod = InstalledMod(game_id=game.id, name="MyREDmod", staging_dir="MyREDmod")
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="mods/MyREDmod/info.json",
            source_path="mods/MyREDmod/info.json",
            link_kind="junction",
        )
    )
    session.commit()

    plan, skipped = plan_deploy(game, session)
    assert plan.is_empty
    assert skipped == 1


def test_redmod_deploy_skipped_when_binary_missing(tmp_path):
    g = make_game(tmp_path)
    result = redmod_deploy(g)
    assert result.ran is False
    assert "not found" in result.skipped_reason.lower()


def test_redmod_deploy_invokes_subprocess_with_expected_args(tmp_path):
    g = make_game(tmp_path)
    exe = _stage_redmod_binary(g)
    proc = _make_redmod_proc(returncode=0, stdout="deployed")
    with patch(
        "rippermod_manager.services.vfs.deploy_service.subprocess.run", return_value=proc
    ) as mocked:
        result = redmod_deploy(g)

    assert result.ran is True
    assert result.success is True
    assert result.returncode == 0
    assert "deployed" in result.stdout
    mocked.assert_called_once()
    args, kwargs = mocked.call_args
    cmd = args[0]
    assert cmd[0] == str(exe)
    assert cmd[1:] == ["deploy", "-reportProgress"]
    assert kwargs["cwd"] == str(exe.parent)
    assert kwargs["shell"] is False
    assert kwargs["capture_output"] is True


def test_redmod_deploy_captures_nonzero_exit(tmp_path):
    g = make_game(tmp_path)
    _stage_redmod_binary(g)
    proc = _make_redmod_proc(returncode=1, stdout="", stderr="boom")
    with patch("rippermod_manager.services.vfs.deploy_service.subprocess.run", return_value=proc):
        result = redmod_deploy(g)

    assert result.ran is True
    assert result.success is False
    assert result.returncode == 1
    assert "boom" in result.error


def test_redmod_deploy_handles_timeout(tmp_path):
    g = make_game(tmp_path)
    _stage_redmod_binary(g)
    with patch(
        "rippermod_manager.services.vfs.deploy_service.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="redmod", timeout=600),
    ):
        result = redmod_deploy(g)

    assert result.ran is True
    assert result.success is False
    assert "timed out" in result.error.lower()


def test_deploy_runs_redmod_when_redmod_content_present(in_memory_session, sample_game):
    """deploy() should auto-invoke redMod.exe when any enabled mod has files under mods/."""
    session = in_memory_session
    game = sample_game
    _stage_redmod_binary(game)

    staging = Path(game.install_path) / "downloaded_mods" / "MyREDmod" / "mods" / "MyREDmod"
    staging.mkdir(parents=True)
    (staging / "info.json").write_text("{}")

    mod = InstalledMod(game_id=game.id, name="MyREDmod", staging_dir="MyREDmod", disabled=False)
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="mods/MyREDmod/info.json",
            source_path="mods/MyREDmod/info.json",
            link_kind="junction",
        )
    )
    session.commit()

    proc = _make_redmod_proc(returncode=0, stdout="compiled 1 mod")
    with (
        patch(
            "rippermod_manager.services.vfs.deploy_service.is_game_running",
            return_value=False,
        ),
        patch(
            "rippermod_manager.services.vfs.deploy_service.junction",
            side_effect=lambda src, dst: Path(dst).mkdir(parents=True, exist_ok=True),
        ),
        patch(
            "rippermod_manager.services.vfs.deploy_service.subprocess.run",
            return_value=proc,
        ) as redmod_run,
    ):
        report = deploy(game, session)

    assert report.failed == 0
    assert report.redmod is not None
    assert report.redmod.ran is True
    assert report.redmod.success is True
    redmod_run.assert_called_once()


def test_deploy_skips_redmod_when_only_legacy_archives(in_memory_session, sample_game):
    """deploy() must not invoke redMod.exe when no enabled mod has mods/ content."""
    session = in_memory_session
    game = sample_game
    _stage_redmod_binary(game)

    staging = Path(game.install_path) / "downloaded_mods" / "LegacyMod" / "archive" / "pc" / "mod"
    staging.mkdir(parents=True)
    (staging / "thing.archive").write_text("x")

    mod = InstalledMod(game_id=game.id, name="LegacyMod", staging_dir="LegacyMod", disabled=False)
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="archive/pc/mod/thing.archive",
            source_path="archive/pc/mod/thing.archive",
            link_kind="hardlink",
        )
    )
    session.commit()

    with (
        patch(
            "rippermod_manager.services.vfs.deploy_service.is_game_running",
            return_value=False,
        ),
        patch("rippermod_manager.services.vfs.deploy_service.subprocess.run") as redmod_run,
    ):
        report = deploy(game, session)

    assert report.failed == 0
    assert report.redmod is None
    redmod_run.assert_not_called()
