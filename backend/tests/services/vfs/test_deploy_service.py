import os
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import DeployJournalEntry, InstalledMod, InstalledModFile
from rippermod_manager.schemas.deploy import DeployOp, DeployPlan
from rippermod_manager.services.vfs.deploy_service import (
    deploy,
    execute_plan,
    plan_deploy,
    pre_flight_check,
    undeploy,
)


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

    plan = plan_deploy(game, session)

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

    plan = plan_deploy(game, session)
    assert plan.is_empty


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

    plan = plan_deploy(game, session)
    junction_ops = [op for op in plan.ops if op.operation == "junction"]
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
