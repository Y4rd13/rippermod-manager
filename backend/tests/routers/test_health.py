"""Tests for the pre-launch health check: GET /games/{game}/health."""

from sqlmodel import Session

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusModRequirement


def _make_game(session: Session) -> Game:
    game = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path="/games/x")
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


class TestHealthCheck:
    def test_healthy_setup_is_ok(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            s.add(
                InstalledMod(
                    game_id=game.id, name="ModA", nexus_mod_id=100, disabled=False, deployed=True
                )
            )
            s.commit()

        resp = client.get("/api/v1/games/Cyberpunk 2077/health/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["critical"] == 0

    def test_missing_requirement_is_critical(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            # AddonMod (200) requires BaseMod (100), which is NOT installed.
            s.add(
                InstalledMod(
                    game_id=game.id,
                    name="AddonMod",
                    nexus_mod_id=200,
                    disabled=False,
                    deployed=True,
                )
            )
            s.add(
                NexusModRequirement(
                    nexus_mod_id=200, required_mod_id=100, mod_name="BaseMod", is_external=False
                )
            )
            s.commit()

        resp = client.get("/api/v1/games/Cyberpunk 2077/health/")
        data = resp.json()
        assert data["ok"] is False
        assert data["critical"] >= 1
        kinds = {i["kind"] for i in data["issues"]}
        assert "missing_requirement" in kinds
        miss = next(i for i in data["issues"] if i["kind"] == "missing_requirement")
        assert miss["mod_name"] == "AddonMod"

    def test_disabled_requirement_is_warning(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            # BaseMod (100) is installed but disabled; AddonMod (200) requires it.
            s.add(
                InstalledMod(
                    game_id=game.id, name="BaseMod", nexus_mod_id=100, disabled=True, deployed=True
                )
            )
            s.add(
                InstalledMod(
                    game_id=game.id,
                    name="AddonMod",
                    nexus_mod_id=200,
                    disabled=False,
                    deployed=True,
                )
            )
            s.add(
                NexusModRequirement(
                    nexus_mod_id=200, required_mod_id=100, mod_name="BaseMod", is_external=False
                )
            )
            s.commit()

        resp = client.get("/api/v1/games/Cyberpunk 2077/health/")
        data = resp.json()
        assert data["ok"] is True  # warning, not critical
        kinds = {i["kind"] for i in data["issues"]}
        assert "disabled_requirement" in kinds

    def test_enabled_but_not_deployed_is_warning(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            s.add(
                InstalledMod(
                    game_id=game.id, name="ModA", nexus_mod_id=100, disabled=False, deployed=False
                )
            )
            s.commit()

        resp = client.get("/api/v1/games/Cyberpunk 2077/health/")
        data = resp.json()
        assert data["warning"] >= 1
        kinds = {i["kind"] for i in data["issues"]}
        assert "failed_install" in kinds

    def test_404_unknown_game(self, client):
        resp = client.get("/api/v1/games/Nonexistent/health/")
        assert resp.status_code == 404

    def test_outdated_mod_is_info(self, client, engine, monkeypatch):
        from rippermod_manager.services import update_service
        from rippermod_manager.services.update_service import UpdateResult

        with Session(engine) as s:
            _make_game(s)

        def fake_check(game_id, game_domain, session):
            return UpdateResult(
                total_checked=1,
                updates=[
                    {
                        "installed_mod_id": 5,
                        "display_name": "OldMod",
                        "reason": "Newer version available: v2.0",
                    }
                ],
            )

        monkeypatch.setattr(update_service, "check_cached_updates", fake_check)
        resp = client.get("/api/v1/games/Cyberpunk 2077/health/")
        data = resp.json()
        outdated = [i for i in data["issues"] if i["kind"] == "outdated"]
        assert len(outdated) == 1
        assert outdated[0]["mod_name"] == "OldMod"  # from the "display_name" key
        assert outdated[0]["severity"] == "info"
        assert "v2.0" in outdated[0]["message"]  # from the "reason" key

    def test_handles_missing_game_dir_gracefully(self, client, engine):
        # Installed mods + a non-existent install_path: the drift/untracked scans
        # must degrade gracefully (OSError guards) without crashing the endpoint.
        with Session(engine) as s:
            game = _make_game(s)
            s.add(
                InstalledMod(
                    game_id=game.id, name="ModA", nexus_mod_id=100, disabled=False, deployed=True
                )
            )
            s.commit()

        resp = client.get("/api/v1/games/Cyberpunk 2077/health/")
        assert resp.status_code == 200
        kinds = {i["kind"] for i in resp.json()["issues"]}
        assert "foreign_files" not in kinds
        assert "untracked_files" not in kinds
