"""Tests for the diagnostics export: GET /diagnostics."""

from sqlmodel import Session

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.settings import AppSetting


class TestDiagnostics:
    def test_bundle_structure(self, client, engine):
        with Session(engine) as s:
            game = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path="/games/x")
            s.add(game)
            s.commit()
            s.refresh(game)
            s.add(
                InstalledMod(
                    game_id=game.id,
                    name="ModA",
                    nexus_mod_id=100,
                    installed_version="1.2",
                    disabled=False,
                )
            )
            s.commit()

        resp = client.get("/api/v1/diagnostics/")
        assert resp.status_code == 200
        data = resp.json()
        assert "generated_at" in data
        assert "system" in data
        assert isinstance(data["log_tail"], list)

        games = data["games"]
        assert len(games) == 1
        assert games[0]["name"] == "Cyberpunk 2077"
        mods = games[0]["mods"]
        assert len(mods) == 1
        assert mods[0]["name"] == "ModA"
        assert mods[0]["version"] == "1.2"
        assert mods[0]["enabled"] is True

    def test_does_not_leak_secrets(self, client, engine):
        # A configured API key value must never appear in the diagnostics bundle.
        with Session(engine) as s:
            s.add(AppSetting(key="nexus_api_key", value="SECRET-KEY-DO-NOT-LEAK"))
            s.commit()

        resp = client.get("/api/v1/diagnostics/")
        assert resp.status_code == 200
        assert "SECRET-KEY-DO-NOT-LEAK" not in resp.text
