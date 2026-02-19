class TestListUpdates:
    def test_game_not_found(self, client):
        r = client.get("/api/v1/games/NoGame/updates/")
        assert r.status_code == 404

    def test_no_correlations_empty(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.get("/api/v1/games/G/updates/")
        assert r.status_code == 200
        data = r.json()
        assert data["total_checked"] == 0
        assert data["updates"] == []

    def test_no_version_diff_empty(self, client, engine):
        from sqlmodel import Session

        from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
        from chat_nexus_mod_manager.models.game import Game, GameModPath
        from chat_nexus_mod_manager.models.mod import ModGroup
        from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod1")
            s.add(group)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=10, mod_name="Mod1", version="1.0")
            s.add(dl)
            s.flush()
            s.add(ModNexusCorrelation(mod_group_id=group.id, nexus_download_id=dl.id, score=1.0, method="exact"))
            s.add(NexusModMeta(nexus_mod_id=10, name="Mod1", version="1.0"))
            s.commit()

        r = client.get("/api/v1/games/G/updates/")
        assert r.json()["updates_available"] == 0

    def test_version_mismatch_returns_update(self, client, engine):
        from sqlmodel import Session

        from chat_nexus_mod_manager.models.correlation import ModNexusCorrelation
        from chat_nexus_mod_manager.models.game import Game, GameModPath
        from chat_nexus_mod_manager.models.mod import ModGroup
        from chat_nexus_mod_manager.models.nexus import NexusDownload, NexusModMeta

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="Mod1")
            s.add(group)
            dl = NexusDownload(game_id=game.id, nexus_mod_id=10, mod_name="Mod1", version="1.0", nexus_url="https://nexus/10")
            s.add(dl)
            s.flush()
            s.add(ModNexusCorrelation(mod_group_id=group.id, nexus_download_id=dl.id, score=1.0, method="exact"))
            s.add(NexusModMeta(nexus_mod_id=10, name="Mod1", version="2.0", author="Auth"))
            s.commit()

        r = client.get("/api/v1/games/G/updates/")
        data = r.json()
        assert data["updates_available"] == 1
        assert data["updates"][0]["local_version"] == "1.0"
        assert data["updates"][0]["nexus_version"] == "2.0"


class TestCheckUpdates:
    def test_no_key(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.post("/api/v1/games/G/updates/check")
        assert r.status_code == 200
        assert r.json()["total_checked"] == 0
