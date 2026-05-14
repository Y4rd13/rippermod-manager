from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.vfs.deploy_service import plan_deploy, pre_flight_check


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
