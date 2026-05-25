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

    def test_redacted_flag_reflects_param(self, client, engine):
        with Session(engine) as s:
            s.add(Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path="/games/x"))
            s.commit()

        assert client.get("/api/v1/diagnostics/").json()["redacted"] is False
        assert client.get("/api/v1/diagnostics/?redact=true").json()["redacted"] is True

    def test_redact_replaces_home_dir_in_paths(self, client, engine):
        # With redact on, a path under the user's home dir is anonymised to ~,
        # so the OS username doesn't leak when the report is shared.
        from pathlib import Path

        home = str(Path.home())
        with Session(engine) as s:
            s.add(
                Game(
                    name="Cyberpunk 2077",
                    domain_name="cyberpunk2077",
                    install_path=f"{home}/Games/CP2077",
                )
            )
            s.commit()

        plain = client.get("/api/v1/diagnostics/").json()
        assert plain["games"][0]["install_path"] == f"{home}/Games/CP2077"

        red = client.get("/api/v1/diagnostics/?redact=true").json()
        assert red["games"][0]["install_path"] == "~/Games/CP2077"


class TestScrubSecrets:
    def test_masks_credential_values_but_keeps_content(self):
        from rippermod_manager.services.diagnostics_service import _scrub_secrets

        assert "MY-KEY" not in _scrub_secrets("APIKEY: MY-KEY")
        assert "topsecret" not in _scrub_secrets("api_key=topsecret loaded")
        assert "abc123" not in _scrub_secrets("GET https://cdn/file?key=abc123&expires=9")
        # ordinary log content is preserved
        assert _scrub_secrets("loaded RED4ext plugin") == "loaded RED4ext plugin"
