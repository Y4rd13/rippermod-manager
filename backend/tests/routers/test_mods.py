from unittest.mock import patch

import pytest

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

    def test_list_mods_exposes_endorse_and_track_flags(self, client, engine):
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
            for display, nexus_id, flag in (("Liked", 4885, True), ("Plain", 28966, False)):
                group = ModGroup(game_id=game.id, display_name=display, confidence=0.9)
                nd = NexusDownload(
                    game_id=game.id,
                    nexus_mod_id=nexus_id,
                    mod_name=display,
                    is_endorsed=flag,
                    is_tracked=flag,
                )
                s.add(group)
                s.add(nd)
                s.flush()
                s.add(
                    ModNexusCorrelation(
                        mod_group_id=group.id,
                        nexus_download_id=nd.id,
                        score=0.9,
                        method="filename_id",
                    )
                )
            s.commit()

        r = client.get("/api/v1/games/G/mods/")
        by_name = {g["display_name"]: g["nexus_match"] for g in r.json()}
        assert (by_name["Liked"]["is_endorsed"], by_name["Liked"]["is_tracked"]) == (True, True)
        assert (by_name["Plain"]["is_endorsed"], by_name["Plain"]["is_tracked"]) == (False, False)


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


def _pairs(session, group_id):
    from sqlmodel import select

    from rippermod_manager.models.correlation import ModNexusCorrelation
    from rippermod_manager.models.nexus import NexusDownload

    session.expire_all()
    rows = session.exec(
        select(ModNexusCorrelation, NexusDownload)
        .join(NexusDownload, NexusDownload.id == ModNexusCorrelation.nexus_download_id)
        .where(ModNexusCorrelation.mod_group_id == group_id)
    ).all()
    return {(corr.mod_group_id, dl.nexus_mod_id) for corr, dl in rows}


@pytest.fixture
def matched_group(client, session, make_game):
    """A group the correlator matched by exact name to Nexus mod 555."""
    from rippermod_manager.models.mod import ModGroup
    from rippermod_manager.models.nexus import NexusDownload

    game = make_game(name="G")
    group = ModGroup(game_id=game.id, display_name="Cool Mod")
    session.add(group)
    session.add(NexusDownload(game_id=game.id, nexus_mod_id=555, mod_name="Cool Mod"))
    session.commit()
    r = client.post(f"/api/v1/games/{game.name}/mods/correlate")
    assert r.status_code == 200
    assert _pairs(session, group.id) == {(group.id, 555)}
    return game, group, 555


class TestRejectedMatchesAreRemembered:
    def test_reject_is_remembered_across_correlate(self, client, session, matched_group):
        game, group, _nexus_mod_id = matched_group
        client.delete(f"/api/v1/games/{game.name}/mods/{group.id}/correlation")
        client.post(f"/api/v1/games/{game.name}/mods/correlate")
        assert _pairs(session, group.id) == set()

    def test_reject_stores_the_nexus_mod_id(self, client, session, matched_group):
        from sqlmodel import select

        from rippermod_manager.models.correlation import RejectedCorrelation

        game, group, nexus_mod_id = matched_group
        client.delete(f"/api/v1/games/{game.name}/mods/{group.id}/correlation")
        rows = session.exec(select(RejectedCorrelation)).all()
        assert [(r.mod_group_id, r.nexus_mod_id) for r in rows] == [(group.id, nexus_mod_id)]

    def test_confirm_clears_rejection(self, client, session, matched_group):
        from sqlmodel import select

        from rippermod_manager.models.correlation import RejectedCorrelation

        game, group, nexus_mod_id = matched_group
        client.delete(f"/api/v1/games/{game.name}/mods/{group.id}/correlation")
        r = client.put(
            f"/api/v1/games/{game.name}/mods/{group.id}/correlation",
            json={"nexus_mod_id": nexus_mod_id},
        )
        assert r.status_code == 200
        session.expire_all()
        assert session.exec(select(RejectedCorrelation)).all() == []
        assert _pairs(session, group.id) == {(group.id, nexus_mod_id)}

    def test_reassign_to_other_mod_keeps_rejection(self, client, session, matched_group):
        from sqlmodel import select

        from rippermod_manager.models.correlation import RejectedCorrelation
        from rippermod_manager.models.nexus import NexusDownload

        game, group, nexus_mod_id = matched_group
        session.add(NexusDownload(game_id=game.id, nexus_mod_id=777, mod_name="Other"))
        session.commit()
        client.delete(f"/api/v1/games/{game.name}/mods/{group.id}/correlation")
        client.put(
            f"/api/v1/games/{game.name}/mods/{group.id}/correlation",
            json={"nexus_mod_id": 777},
        )
        session.expire_all()
        rows = session.exec(select(RejectedCorrelation)).all()
        assert [(r.mod_group_id, r.nexus_mod_id) for r in rows] == [(group.id, nexus_mod_id)]

    def test_rejection_is_per_group(self, client, session, matched_group):
        """Rejecting group A's match does not block the same mod for group B."""
        from rippermod_manager.models.mod import ModGroup

        game, group, nexus_mod_id = matched_group
        client.delete(f"/api/v1/games/{game.name}/mods/{group.id}/correlation")
        other = ModGroup(game_id=game.id, display_name="Cool Mod")
        session.add(other)
        session.commit()
        client.post(f"/api/v1/games/{game.name}/mods/correlate")
        assert _pairs(session, group.id) == set()
        assert _pairs(session, other.id) == {(other.id, nexus_mod_id)}

    def test_deleting_the_game_removes_its_rejections(self, client, session, matched_group):
        from sqlmodel import select

        from rippermod_manager.models.correlation import RejectedCorrelation

        game, group, _nexus_mod_id = matched_group
        client.delete(f"/api/v1/games/{game.name}/mods/{group.id}/correlation")
        assert len(session.exec(select(RejectedCorrelation)).all()) == 1

        assert client.delete(f"/api/v1/games/{game.name}").status_code == 204
        session.expire_all()
        assert session.exec(select(RejectedCorrelation)).all() == []

    def test_correlator_falls_to_next_best_when_best_is_rejected(
        self, client, session, matched_group
    ):
        from rippermod_manager.models.nexus import NexusDownload

        game, group, _nexus_mod_id = matched_group
        session.add(NexusDownload(game_id=game.id, nexus_mod_id=777, mod_name="Cool Mod Extended"))
        session.commit()
        client.delete(f"/api/v1/games/{game.name}/mods/{group.id}/correlation")
        client.post(f"/api/v1/games/{game.name}/mods/correlate")
        assert _pairs(session, group.id) == {(group.id, 777)}


class TestMatchersSkipRejectedPairs:
    def _reject(self, session, group, nexus_mod_id):
        from rippermod_manager.models.correlation import RejectedCorrelation

        session.add(RejectedCorrelation(mod_group_id=group.id, nexus_mod_id=nexus_mod_id))
        session.commit()

    @pytest.mark.asyncio
    async def test_requirement_matcher(self, session, make_game):
        from rippermod_manager.models.correlation import ModNexusCorrelation
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload, NexusModRequirement
        from rippermod_manager.services.requirement_matcher import match_by_requirements

        game = make_game()
        main = ModGroup(game_id=game.id, display_name="Main Mod")
        dep = ModGroup(game_id=game.id, display_name="Required Dependency")
        session.add_all([main, dep])
        dl = NexusDownload(game_id=game.id, nexus_mod_id=100, mod_name="Main Mod")
        session.add(dl)
        session.flush()
        session.add(
            ModNexusCorrelation(mod_group_id=main.id, nexus_download_id=dl.id, method="exact")
        )
        session.add(
            NexusModRequirement(
                nexus_mod_id=100, required_mod_id=200, mod_name="Required Dependency"
            )
        )
        session.commit()
        self._reject(session, dep, 200)

        result = await match_by_requirements(game, session)

        assert result.matched == 0
        assert _pairs(session, dep.id) == set()

    def test_endorsed_name_matcher(self, session, make_game):
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload
        from rippermod_manager.services.file_list_matcher import match_endorsed_by_name

        game = make_game()
        group = ModGroup(game_id=game.id, display_name="Cool Mod")
        session.add(group)
        session.add(
            NexusDownload(game_id=game.id, nexus_mod_id=555, mod_name="Cool Mod", is_endorsed=True)
        )
        session.commit()
        self._reject(session, group, 555)

        result = match_endorsed_by_name(game, session)

        assert result.matched == 0
        assert _pairs(session, group.id) == set()

    def test_correlator_filename_id_and_installed_paths(self, session, make_game):
        from rippermod_manager.matching.correlator import correlate_game_mods
        from rippermod_manager.models.install import InstalledMod
        from rippermod_manager.models.mod import ModFile, ModGroup
        from rippermod_manager.models.nexus import NexusDownload

        game = make_game()
        by_file = ModGroup(game_id=game.id, display_name="Zzz Unrelated")
        by_install = ModGroup(game_id=game.id, display_name="Qqq Other")
        session.add_all([by_file, by_install])
        session.add_all(
            [
                NexusDownload(game_id=game.id, nexus_mod_id=4885, mod_name="Aaa"),
                NexusDownload(game_id=game.id, nexus_mod_id=999, mod_name="Bbb"),
            ]
        )
        session.flush()
        session.add(
            ModFile(
                mod_group_id=by_file.id,
                file_path="mods/x-4885-1-0.archive",
                filename="Aaa-4885-1-0.archive",
            )
        )
        session.add(
            InstalledMod(
                game_id=game.id,
                name="Bbb",
                mod_group_id=by_install.id,
                nexus_mod_id=999,
            )
        )
        session.commit()
        self._reject(session, by_file, 4885)
        self._reject(session, by_install, 999)

        correlate_game_mods(game, session)

        assert _pairs(session, by_file.id) == set()
        assert _pairs(session, by_install.id) == set()


class TestRejectRemembersOnlyTheVisiblePair:
    def test_reject_stores_only_the_top_scored_pair(self, client, session, make_game):
        from sqlmodel import select

        from rippermod_manager.models.correlation import ModNexusCorrelation, RejectedCorrelation
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload

        game = make_game(name="G")
        group = ModGroup(game_id=game.id, display_name="Some Mod")
        dl_a = NexusDownload(game_id=game.id, nexus_mod_id=111, mod_name="A")
        dl_b = NexusDownload(game_id=game.id, nexus_mod_id=222, mod_name="B")
        session.add_all([group, dl_a, dl_b])
        session.flush()
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id, nexus_download_id=dl_a.id, score=0.9, method="exact"
            )
        )
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id, nexus_download_id=dl_b.id, score=0.6, method="fuzzy"
            )
        )
        session.commit()

        r = client.delete(f"/api/v1/games/{game.name}/mods/{group.id}/correlation")

        assert r.status_code == 200
        session.expire_all()
        rows = session.exec(select(RejectedCorrelation)).all()
        assert [(x.mod_group_id, x.nexus_mod_id) for x in rows] == [(group.id, 111)]
        assert _pairs(session, group.id) == set()

    def test_confirm_clears_the_rejection_of_its_pair(self, client, session, make_game):
        from sqlmodel import select

        from rippermod_manager.models.correlation import ModNexusCorrelation, RejectedCorrelation
        from rippermod_manager.models.mod import ModGroup
        from rippermod_manager.models.nexus import NexusDownload

        game = make_game(name="G")
        group = ModGroup(game_id=game.id, display_name="Some Mod")
        dl = NexusDownload(game_id=game.id, nexus_mod_id=111, mod_name="A")
        session.add_all([group, dl])
        session.flush()
        session.add(RejectedCorrelation(mod_group_id=group.id, nexus_mod_id=111))
        session.add(
            ModNexusCorrelation(
                mod_group_id=group.id, nexus_download_id=dl.id, score=0.9, method="exact"
            )
        )
        session.commit()

        r = client.patch(f"/api/v1/games/{game.name}/mods/{group.id}/correlation/confirm")

        assert r.status_code == 200
        session.expire_all()
        assert session.exec(select(RejectedCorrelation)).all() == []


class TestCorrelationEndpointsReportOnDisk:
    def test_confirm_correlation_reports_on_disk(self, client, matched_group):
        game, group, _nexus_mod_id = matched_group
        r = client.patch(f"/api/v1/games/{game.name}/mods/{group.id}/correlation/confirm")
        assert r.status_code == 200
        assert r.json()["confirmed"] is True
        assert r.json()["on_disk"] is True

    def test_reassign_correlation_reports_on_disk(self, client, matched_group):
        game, group, nexus_mod_id = matched_group
        r = client.put(
            f"/api/v1/games/{game.name}/mods/{group.id}/correlation",
            json={"nexus_mod_id": nexus_mod_id},
        )
        assert r.status_code == 200
        assert r.json()["on_disk"] is True
