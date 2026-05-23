"""Tests for the activity log: GET endpoint + record_activity service."""

import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.activity import ActivityLog
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.services import activity_service
from rippermod_manager.services.activity_service import record_activity
from rippermod_manager.services.install_service import install_mod, toggle_mod, uninstall_mod


def _make_game(session: Session, name: str, domain: str) -> Game:
    game = Game(name=name, domain_name=domain, install_path="/games/x")
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


def _make_real_game(session: Session, tmp_path) -> Game:
    """A Cyberpunk game backed by a real on-disk dir so install/uninstall work."""
    install = tmp_path / "game"
    (install / "downloaded_mods").mkdir(parents=True)
    game = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(install))
    session.add(game)
    session.flush()
    session.add(GameModPath(game_id=game.id, relative_path="mods"))
    session.commit()
    session.refresh(game)
    return game


def _sample_archive(staging: Path, name: str = "SampleMod-v1.zip") -> Path:
    archive = staging / name
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("r6/scripts/foo.reds", b"// sample")
    return archive


class TestActivityLog:
    def test_records_and_lists_newest_first(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            record_activity(s, game_id=game.id, action="install", target="ModA", detail="3 files")
            record_activity(s, game_id=game.id, action="disable", target="ModB")

        resp = client.get("/api/v1/games/Cyberpunk 2077/activity/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # newest first
        assert data[0]["action"] == "disable"
        assert data[0]["target"] == "ModB"
        assert data[1]["action"] == "install"
        assert data[1]["detail"] == "3 files"

    def test_scoped_per_game(self, client, engine):
        with Session(engine) as s:
            g1 = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            g2 = _make_game(s, "Skyrim", "skyrimspecialedition")
            record_activity(s, game_id=g1.id, action="install", target="CP Mod")
            record_activity(s, game_id=g2.id, action="install", target="SK Mod")

        resp = client.get("/api/v1/games/Cyberpunk 2077/activity/")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["target"] == "CP Mod"

    def test_limit_clamped(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            for i in range(5):
                record_activity(s, game_id=game.id, action="install", target=f"Mod{i}")

        resp = client.get("/api/v1/games/Cyberpunk 2077/activity/?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_404_unknown_game(self, client):
        resp = client.get("/api/v1/games/Nonexistent/activity/")
        assert resp.status_code == 404

    def test_prune_caps_entries(self, client, engine, monkeypatch):
        monkeypatch.setattr(activity_service, "MAX_ENTRIES_PER_GAME", 5)
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            for i in range(8):
                record_activity(s, game_id=game.id, action="install", target=f"Mod{i}")

        resp = client.get("/api/v1/games/Cyberpunk 2077/activity/?limit=1000")
        data = resp.json()
        assert len(data) == 5  # pruned to cap
        assert data[0]["target"] == "Mod7"  # newest survives
        assert data[-1]["target"] == "Mod3"  # Mod0..2 pruned


class TestActivityUndo:
    def test_undo_install_uninstalls(self, client, engine, tmp_path):
        with Session(engine) as s:
            game = _make_real_game(s, tmp_path)
            archive = _sample_archive(Path(game.install_path) / "downloaded_mods")
            result = install_mod(game, archive, s, auto_deploy=False)
            mod_id = result.installed_mod_id

        acts = client.get("/api/v1/games/Cyberpunk 2077/activity/").json()
        install_entry = next(a for a in acts if a["action"] == "install")
        assert install_entry["undoable"] is True

        resp = client.post(f"/api/v1/games/Cyberpunk 2077/activity/{install_entry['id']}/undo")
        assert resp.status_code == 200
        assert resp.json()["undone_at"] is not None

        with Session(engine) as s:
            assert s.get(InstalledMod, mod_id) is None  # install undone -> uninstalled

    def test_undo_disable_reenables(self, client, engine, tmp_path):
        with Session(engine) as s:
            game = _make_real_game(s, tmp_path)
            archive = _sample_archive(Path(game.install_path) / "downloaded_mods")
            result = install_mod(game, archive, s, auto_deploy=False)
            mod = s.get(InstalledMod, result.installed_mod_id)
            toggle_mod(mod, game, s)  # disable -> records a "disable" entry
            assert mod.disabled is True
            mod_id = result.installed_mod_id

        acts = client.get("/api/v1/games/Cyberpunk 2077/activity/").json()
        disable_entry = next(a for a in acts if a["action"] == "disable")

        resp = client.post(f"/api/v1/games/Cyberpunk 2077/activity/{disable_entry['id']}/undo")
        assert resp.status_code == 200

        with Session(engine) as s:
            assert s.get(InstalledMod, mod_id).disabled is False  # re-enabled

    def test_undo_non_undoable_is_409(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            record_activity(s, game_id=game.id, action="deploy", target="12 files")

        acts = client.get("/api/v1/games/Cyberpunk 2077/activity/").json()
        resp = client.post(f"/api/v1/games/Cyberpunk 2077/activity/{acts[0]['id']}/undo")
        assert resp.status_code == 409

    def test_undo_stale_mod_is_409(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            record_activity(
                s,
                game_id=game.id,
                action="install",
                target="GhostMod",
                installed_mod_id=99999,
                undoable=True,
            )

        acts = client.get("/api/v1/games/Cyberpunk 2077/activity/").json()
        resp = client.post(f"/api/v1/games/Cyberpunk 2077/activity/{acts[0]['id']}/undo")
        assert resp.status_code == 409

    def test_undo_already_undone_is_409(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            s.add(
                ActivityLog(
                    game_id=game.id,
                    action="install",
                    target="X",
                    installed_mod_id=1,
                    undoable=True,
                    undone_at=datetime.now(UTC),
                )
            )
            s.commit()

        acts = client.get("/api/v1/games/Cyberpunk 2077/activity/").json()
        resp = client.post(f"/api/v1/games/Cyberpunk 2077/activity/{acts[0]['id']}/undo")
        assert resp.status_code == 409

    def test_undo_wrong_game_is_404(self, client, engine):
        with Session(engine) as s:
            _make_game(s, "Cyberpunk 2077", "cyberpunk2077")
            g2 = _make_game(s, "Skyrim", "skyrimspecialedition")
            record_activity(
                s,
                game_id=g2.id,
                action="install",
                target="SKMod",
                installed_mod_id=1,
                undoable=True,
            )

        acts = client.get("/api/v1/games/Skyrim/activity/").json()
        # undo g2's entry through g1's URL -> 404 (not this game's entry)
        resp = client.post(f"/api/v1/games/Cyberpunk 2077/activity/{acts[0]['id']}/undo")
        assert resp.status_code == 404

    def test_undo_uninstall_reinstalls(self, client, engine, tmp_path):
        with Session(engine) as s:
            game = _make_real_game(s, tmp_path)
            game_id = game.id
            archive = _sample_archive(Path(game.install_path) / "downloaded_mods")
            result = install_mod(game, archive, s, auto_deploy=False)
            uninstall_mod(s.get(InstalledMod, result.installed_mod_id), game, s)
            assert s.get(InstalledMod, result.installed_mod_id) is None

        acts = client.get("/api/v1/games/Cyberpunk 2077/activity/").json()
        uninstall_entry = next(a for a in acts if a["action"] == "uninstall")
        assert uninstall_entry["undoable"] is True

        resp = client.post(f"/api/v1/games/Cyberpunk 2077/activity/{uninstall_entry['id']}/undo")
        assert resp.status_code == 200

        with Session(engine) as s:
            mods = s.exec(select(InstalledMod).where(InstalledMod.game_id == game_id)).all()
            assert len(mods) == 1  # reinstalled from the original archive
        # The undo appended exactly one (non-undoable) "undo" row -- no duplicate
        # "install" entry from the internal install_mod call.
        acts = client.get("/api/v1/games/Cyberpunk 2077/activity/").json()
        undo_rows = [a for a in acts if a["action"] == "undo"]
        assert len(undo_rows) == 1
        assert undo_rows[0]["undoable"] is False
        assert sum(1 for a in acts if a["action"] == "install") == 1  # only the original

    def test_undo_uninstall_missing_archive_is_409(self, client, engine, tmp_path):
        with Session(engine) as s:
            game = _make_real_game(s, tmp_path)
            archive = _sample_archive(Path(game.install_path) / "downloaded_mods")
            result = install_mod(game, archive, s, auto_deploy=False)
            uninstall_mod(s.get(InstalledMod, result.installed_mod_id), game, s)
            archive.unlink()  # original archive gone -> reinstall can't run

        acts = client.get("/api/v1/games/Cyberpunk 2077/activity/").json()
        uninstall_entry = next(a for a in acts if a["action"] == "uninstall")

        resp = client.post(f"/api/v1/games/Cyberpunk 2077/activity/{uninstall_entry['id']}/undo")
        assert resp.status_code == 409
