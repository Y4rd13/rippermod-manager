"""Tests for the pre-launch health check: GET /games/{game}/health."""

from sqlmodel import Session

from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload, NexusModRequirement


def _make_game(session: Session) -> Game:
    game = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path="/games/x")
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


def _install_with_files(
    s: Session, game: Game, name: str, nexus_id: int, paths: list[str], *, disabled: bool = False
) -> InstalledMod:
    mod = InstalledMod(
        game_id=game.id, name=name, nexus_mod_id=nexus_id, disabled=disabled, deployed=True
    )
    s.add(mod)
    s.flush()
    for p in paths:
        s.add(InstalledModFile(installed_mod_id=mod.id, relative_path=p))
    return mod


def _addon_requiring_scanned_mod(s: Session, game: Game, score: float | None) -> int | None:
    """AddonMod (200) requires "Mod Settings" (4885); optionally a scanned group matches it.

    Returns the scanned group's id, or None when no group is correlated.
    """
    s.add(
        InstalledMod(
            game_id=game.id, name="AddonMod", nexus_mod_id=200, disabled=False, deployed=True
        )
    )
    s.add(
        NexusModRequirement(
            nexus_mod_id=200, required_mod_id=4885, mod_name="Mod Settings", is_external=False
        )
    )
    group_id = None
    if score is not None:
        group = ModGroup(game_id=game.id, display_name="Mod Settings", confidence=0.9)
        nd = NexusDownload(game_id=game.id, nexus_mod_id=4885, mod_name="Mod Settings")
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
        group_id = group.id
    s.commit()
    return group_id


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

    def test_requirement_on_disk_is_info_with_group(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            group_id = _addon_requiring_scanned_mod(s, game, 1.0)

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        issue = next(i for i in data["issues"] if i["required_name"] == "Mod Settings")
        assert issue["kind"] == "unmanaged_requirement"
        assert issue["severity"] == "info"
        assert (
            issue["message"]
            == 'requires "Mod Settings", which is on disk but not managed by RipperMod.'
        )
        assert issue["mod_group_id"] == group_id
        assert issue["nexus_url"] == "https://www.nexusmods.com/cyberpunk2077/mods/4885"
        assert data["critical"] == 0 and data["ok"] is True

    def test_requirement_possible_match_is_warning(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            _addon_requiring_scanned_mod(s, game, 0.47)

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        issue = next(i for i in data["issues"] if i["required_name"] == "Mod Settings")
        assert issue["kind"] == "missing_requirement"
        assert issue["severity"] == "warning"
        assert (
            issue["message"]
            == 'requires "Mod Settings", which may be on disk (match confidence 47%).'
        )
        assert issue["nexus_url"] == "https://www.nexusmods.com/cyberpunk2077/mods/4885"
        assert data["critical"] == 0 and data["ok"] is True

    def test_requirement_without_match_stays_critical(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            _addon_requiring_scanned_mod(s, game, None)

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        issue = next(i for i in data["issues"] if i["required_name"] == "Mod Settings")
        assert issue["kind"] == "missing_requirement"
        assert issue["severity"] == "critical"
        assert issue["message"] == 'requires "Mod Settings", which is not installed.'
        assert issue["nexus_url"] == "https://www.nexusmods.com/cyberpunk2077/mods/4885"
        assert data["ok"] is False

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

    def test_framework_requirement_not_double_reported(self, client, engine):
        # A mod requires ArchiveXL (nexus 4198, a core framework) which is NOT
        # installed. The Frameworks card owns framework status, so the health
        # check must NOT also report it as a missing requirement.
        with Session(engine) as s:
            game = _make_game(s)
            s.add(
                InstalledMod(
                    game_id=game.id, name="SomeMod", nexus_mod_id=200, disabled=False, deployed=True
                )
            )
            s.add(
                NexusModRequirement(
                    nexus_mod_id=200, required_mod_id=4198, mod_name="ArchiveXL", is_external=False
                )
            )
            s.commit()

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        assert "missing_requirement" not in {i["kind"] for i in data["issues"]}

    def test_missing_requirement_carries_nexus_url(self, client, engine):
        # The "Get on Nexus" action needs the required mod's Nexus page URL.
        with Session(engine) as s:
            game = _make_game(s)
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

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        miss = next(i for i in data["issues"] if i["kind"] == "missing_requirement")
        assert miss["nexus_url"] == "https://www.nexusmods.com/cyberpunk2077/mods/100"
        assert miss["required_name"] == "BaseMod"

    def test_disabled_requirement_carries_action_mod_id(self, client, engine):
        # The "Enable" action targets the disabled REQUIRED mod, not the requiring one.
        with Session(engine) as s:
            game = _make_game(s)
            base = InstalledMod(
                game_id=game.id, name="BaseMod", nexus_mod_id=100, disabled=True, deployed=True
            )
            s.add(base)
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
            s.refresh(base)
            base_id = base.id

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        dis = next(i for i in data["issues"] if i["kind"] == "disabled_requirement")
        assert dis["action_mod_id"] == base_id
        assert dis["required_name"] == "BaseMod"

    def test_health_does_not_report_outdated(self, client, engine):
        # Outdated mods are the Updates tab's domain; the health check no longer
        # re-reports them (that duplicated the Updates count and triple-listed
        # outdated frameworks). The Health view shows a single pointer instead.
        with Session(engine) as s:
            game = _make_game(s)
            s.add(
                InstalledMod(
                    game_id=game.id, name="ModA", nexus_mod_id=100, disabled=False, deployed=True
                )
            )
            s.commit()

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        assert "outdated" not in {i["kind"] for i in data["issues"]}

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


class TestMisplacedFiles:
    def test_all_files_outside_is_warning(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            _install_with_files(
                s, game, "JunkMod", 100, ["ReadmeFolder/readme.txt", "docs/guide.pdf"]
            )
            s.commit()

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        misplaced = [i for i in data["issues"] if i["kind"] == "misplaced_files"]
        assert len(misplaced) == 1
        assert misplaced[0]["severity"] == "warning"
        assert misplaced[0]["mod_name"] == "JunkMod"
        assert "none of its 2" in misplaced[0]["message"]
        assert data["ok"] is True  # warning, not critical -- doesn't block launch

    def test_healthy_layout_has_no_misplaced(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            _install_with_files(
                s,
                game,
                "GoodMod",
                100,
                ["archive/pc/mod/x.archive", "bin/x64/plugins/cyber_engine_tweaks/mods/y/init.lua"],
            )
            s.commit()

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        assert "misplaced_files" not in {i["kind"] for i in data["issues"]}

    def test_partial_outside_is_info(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            _install_with_files(s, game, "MixedMod", 100, ["r6/scripts/a.reds", "JunkDir/b.bin"])
            s.commit()

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        misplaced = [i for i in data["issues"] if i["kind"] == "misplaced_files"]
        assert len(misplaced) == 1
        assert misplaced[0]["severity"] == "info"
        assert "1 of 2" in misplaced[0]["message"]

    def test_redmod_layout_not_misplaced(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            _install_with_files(s, game, "MyREDmod", 100, ["mods/MyREDmod/info.json"])
            s.commit()

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        assert "misplaced_files" not in {i["kind"] for i in data["issues"]}

    def test_disabled_mod_excluded(self, client, engine):
        with Session(engine) as s:
            game = _make_game(s)
            _install_with_files(s, game, "DisabledJunk", 100, ["JunkDir/x.bin"], disabled=True)
            s.commit()

        data = client.get("/api/v1/games/Cyberpunk 2077/health/").json()
        assert "misplaced_files" not in {i["kind"] for i in data["issues"]}
