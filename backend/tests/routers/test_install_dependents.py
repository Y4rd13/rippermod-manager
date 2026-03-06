"""Tests for GET /games/{game_name}/install/installed/{mod_id}/dependents."""

from sqlmodel import Session

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusModRequirement


def _setup_game(session: Session) -> Game:
    game = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path="/games/cp")
    session.add(game)
    session.flush()
    session.add(GameModPath(game_id=game.id, relative_path="mods"))
    session.commit()
    session.refresh(game)
    return game


class TestDependentsEndpoint:
    def test_returns_dependents(self, client, engine):
        with Session(engine) as s:
            game = _setup_game(s)
            # Mod A (nexus 100) is the base mod
            mod_a = InstalledMod(game_id=game.id, name="BaseMod", nexus_mod_id=100)
            # Mod B (nexus 200) depends on mod A
            mod_b = InstalledMod(game_id=game.id, name="AddonMod", nexus_mod_id=200)
            s.add_all([mod_a, mod_b])
            s.flush()

            # Forward requirement: mod 200 requires mod 100
            s.add(NexusModRequirement(nexus_mod_id=200, required_mod_id=100, mod_name="BaseMod"))
            s.commit()

            resp = client.get(
                f"/api/v1/games/Cyberpunk 2077/install/installed/{mod_a.id}/dependents"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1
            assert data["dependents"][0]["name"] == "AddonMod"
            assert data["dependents"][0]["nexus_mod_id"] == 200

    def test_empty_when_no_dependents(self, client, engine):
        with Session(engine) as s:
            game = _setup_game(s)
            mod_a = InstalledMod(game_id=game.id, name="Standalone", nexus_mod_id=100)
            s.add(mod_a)
            s.commit()

            resp = client.get(
                f"/api/v1/games/Cyberpunk 2077/install/installed/{mod_a.id}/dependents"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 0
            assert data["dependents"] == []

    def test_empty_when_no_nexus_id(self, client, engine):
        with Session(engine) as s:
            game = _setup_game(s)
            mod_a = InstalledMod(game_id=game.id, name="LocalMod")
            s.add(mod_a)
            s.commit()

            resp = client.get(
                f"/api/v1/games/Cyberpunk 2077/install/installed/{mod_a.id}/dependents"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 0

    def test_404_for_unknown_mod(self, client, engine):
        with Session(engine) as s:
            _setup_game(s)

        resp = client.get("/api/v1/games/Cyberpunk 2077/install/installed/9999/dependents")
        assert resp.status_code == 404

    def test_excludes_external_requirements(self, client, engine):
        with Session(engine) as s:
            game = _setup_game(s)
            mod_a = InstalledMod(game_id=game.id, name="BaseMod", nexus_mod_id=100)
            mod_b = InstalledMod(game_id=game.id, name="ExtMod", nexus_mod_id=200)
            s.add_all([mod_a, mod_b])
            s.flush()

            # External requirement (should be excluded)
            s.add(
                NexusModRequirement(
                    nexus_mod_id=200,
                    required_mod_id=100,
                    mod_name="BaseMod",
                    is_external=True,
                )
            )
            s.commit()

            resp = client.get(
                f"/api/v1/games/Cyberpunk 2077/install/installed/{mod_a.id}/dependents"
            )
            assert resp.status_code == 200
            assert resp.json()["count"] == 0
