from unittest.mock import patch

from rippermod_manager.schemas.mod import CorrelateResult, ScanResult


class TestListModGroups:
    def test_game_not_found(self, client):
        r = client.get("/api/v1/games/NoGame/mods/")
        assert r.status_code == 404

    def test_empty(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "cyberpunk2077", "install_path": client.cp_install},
        )
        r = client.get("/api/v1/games/G/mods/")
        assert r.status_code == 200
        assert r.json() == []

    def test_with_groups(self, client, engine):
        from sqlmodel import Session

        from rippermod_manager.models.game import Game, GameModPath
        from rippermod_manager.models.mod import ModFile, ModGroup

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            group = ModGroup(game_id=game.id, display_name="TestMod", confidence=0.9)
            s.add(group)
            s.flush()
            s.add(
                ModFile(
                    mod_group_id=group.id,
                    file_path="mods/test.archive",
                    filename="test.archive",
                )
            )
            s.commit()

        r = client.get("/api/v1/games/G/mods/")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["display_name"] == "TestMod"
        assert len(data[0]["files"]) == 1

    def test_list_mods_exposes_on_disk_flag(self, client, engine):
        from sqlmodel import Session

        from rippermod_manager.models.correlation import ModNexusCorrelation
        from rippermod_manager.models.game import Game, GameModPath
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload

        with Session(engine) as s:
            game = Game(name="G", domain_name="g", install_path="/g")
            s.add(game)
            s.flush()
            s.add(GameModPath(game_id=game.id, relative_path="mods"))
            for display, nexus_id, score in (("Sure", 4885, 0.75), ("Maybe", 28966, 0.47)):
                group = ModGroup(game_id=game.id, display_name=display, confidence=0.9)
                nd = NexusDownload(game_id=game.id, nexus_mod_id=nexus_id, mod_name=display)
                s.add(group)
                s.add(nd)
                s.flush()
                s.add(
                    ModNexusCorrelation(
                        mod_group_id=group.id,
                        nexus_download_id=nd.id,
                        score=score,
                        method="filename_id",
                    )
                )
            s.commit()

        r = client.get("/api/v1/games/G/mods/")
        assert r.status_code == 200
        by_name = {g["display_name"]: g["nexus_match"] for g in r.json()}
        assert by_name["Sure"]["on_disk"] is True
        assert by_name["Maybe"]["on_disk"] is False


class TestScanMods:
    def test_scan_mock(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G", "domain_name": "cyberpunk2077", "install_path": client.cp_install},
        )
        with patch(
            "rippermod_manager.scanner.service.scan_game_mods",
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
            json={"name": "G", "domain_name": "cyberpunk2077", "install_path": client.cp_install},
        )
        with patch(
            "rippermod_manager.matching.correlator.correlate_game_mods",
            return_value=CorrelateResult(total_groups=10, matched=7, unmatched=3),
        ):
            r = client.post("/api/v1/games/G/mods/correlate")
        assert r.status_code == 200
        assert r.json()["matched"] == 7
