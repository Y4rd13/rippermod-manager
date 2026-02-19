from unittest.mock import patch

from chat_nexus_mod_manager.schemas.mod import CorrelateResult, ScanResult


class TestListModGroups:
    def test_game_not_found(self, client):
        r = client.get("/api/v1/games/NoGame/mods/")
        assert r.status_code == 404

    def test_empty(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        r = client.get("/api/v1/games/G/mods/")
        assert r.status_code == 200
        assert r.json() == []

    def test_with_groups(self, client, engine):
        from sqlmodel import Session

        from chat_nexus_mod_manager.models.game import Game, GameModPath
        from chat_nexus_mod_manager.models.mod import ModFile, ModGroup

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="TestMod", confidence=0.9)
            s.add(group)
            s.flush()
            s.add(ModFile(mod_group_id=group.id, file_path="mods/test.archive", filename="test.archive"))
            s.commit()

        r = client.get("/api/v1/games/G/mods/")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["display_name"] == "TestMod"
        assert len(data[0]["files"]) == 1


class TestScanMods:
    def test_scan_mock(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        with patch(
            "chat_nexus_mod_manager.scanner.service.scan_game_mods",
            return_value=ScanResult(files_found=5, groups_created=2, new_files=3),
        ):
            r = client.post("/api/v1/games/G/mods/scan")
        assert r.status_code == 200
        assert r.json()["files_found"] == 5

    def test_scan_game_not_found(self, client):
        r = client.post("/api/v1/games/NoGame/mods/scan")
        assert r.status_code == 404


class TestCorrelateMods:
    def test_correlate_mock(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "g", "install_path": "/g"},
        )
        with patch(
            "chat_nexus_mod_manager.matching.correlator.correlate_game_mods",
            return_value=CorrelateResult(total_groups=10, matched=7, unmatched=3),
        ):
            r = client.post("/api/v1/games/G/mods/correlate")
        assert r.status_code == 200
        assert r.json()["matched"] == 7
