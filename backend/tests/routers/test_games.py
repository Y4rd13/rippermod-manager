class TestListGames:
    def test_empty(self, client):
        r = client.get("/api/v1/games/")
        assert r.status_code == 200
        assert r.json() == []


class TestCreateGame:
    def test_success(self, client):
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "TestGame",
                "domain_name": "testgame",
                "install_path": "/games/test",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "TestGame"
        assert data["domain_name"] == "testgame"

    def test_auto_cyberpunk_paths(self, client):
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "Cyberpunk 2077",
                "domain_name": "cyberpunk2077",
                "install_path": "/games/cp2077",
            },
        )
        assert r.status_code == 201
        paths = r.json()["mod_paths"]
        assert len(paths) == 10
        rels = {p["relative_path"] for p in paths}
        assert {"archive/pc/patch", "r6/config"} <= rels

    def test_custom_paths(self, client):
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "Custom",
                "domain_name": "custom",
                "install_path": "/games/custom",
                "mod_paths": [{"relative_path": "mods", "description": "Main"}],
            },
        )
        assert r.status_code == 201
        assert len(r.json()["mod_paths"]) == 1

    def test_duplicate_upserts(self, client):
        payload = {
            "name": "DupGame",
            "domain_name": "dup",
            "install_path": "/games/dup",
        }
        client.post("/api/v1/games/", json=payload)
        r = client.post(
            "/api/v1/games/",
            json={**payload, "install_path": "/games/dup2"},
        )
        assert r.status_code == 200
        assert r.json()["install_path"] == "/games/dup2"


class TestGetGame:
    def test_found(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "G1", "domain_name": "g1", "install_path": "/g1"},
        )
        r = client.get("/api/v1/games/G1")
        assert r.status_code == 200
        assert r.json()["name"] == "G1"

    def test_not_found(self, client):
        r = client.get("/api/v1/games/Nonexistent")
        assert r.status_code == 404

    def test_resolved_mods_dir_default(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "DefDir", "domain_name": "dd", "install_path": "/games/dd"},
        )
        r = client.get("/api/v1/games/DefDir")
        assert r.status_code == 200
        data = r.json()
        assert data["mods_dir"] is None
        assert data["resolved_mods_dir"].replace("\\", "/") == "/games/dd/downloaded_mods"

    def test_resolved_mods_dir_with_override(self, client, tmp_path):
        custom = tmp_path / "staging"
        custom.mkdir()
        client.post(
            "/api/v1/games/",
            json={
                "name": "OvrDir",
                "domain_name": "od",
                "install_path": str(tmp_path),
                "mods_dir": str(custom),
            },
        )
        r = client.get("/api/v1/games/OvrDir")
        assert r.status_code == 200
        data = r.json()
        assert data["mods_dir"] == str(custom)
        assert data["resolved_mods_dir"] == str(custom)

    def test_post_rejects_cross_volume_mods_dir(self, client, monkeypatch, tmp_path):
        # Force same_volume to return False so this works regardless of test env layout.
        from rippermod_manager.routers import games as games_router

        monkeypatch.setattr(games_router, "same_volume", lambda a, b: False)
        install = tmp_path / "game"
        install.mkdir()
        bad_mods_dir = tmp_path / "bad"
        bad_mods_dir.mkdir()
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "CrossVol",
                "domain_name": "cv",
                "install_path": str(install),
                "mods_dir": str(bad_mods_dir),
            },
        )
        assert r.status_code == 422, r.text
        assert "same physical volume" in r.json()["detail"]

    def test_post_accepts_same_volume_mods_dir(self, client, tmp_path):
        install = tmp_path / "game"
        install.mkdir()
        custom = tmp_path / "staging"
        custom.mkdir()
        r = client.post(
            "/api/v1/games/",
            json={
                "name": "SameVol",
                "domain_name": "sv",
                "install_path": str(install),
                "mods_dir": str(custom),
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["mods_dir"] == str(custom)
        assert r.json()["resolved_mods_dir"] == str(custom)


class TestUpdateGame:
    def test_set_mods_dir_same_volume(self, client, tmp_path):
        install = tmp_path / "game"
        install.mkdir()
        custom = tmp_path / "staging"
        custom.mkdir()
        client.post(
            "/api/v1/games/",
            json={"name": "U1", "domain_name": "u", "install_path": str(install)},
        )
        r = client.patch("/api/v1/games/U1", json={"mods_dir": str(custom)})
        assert r.status_code == 200, r.text
        assert r.json()["mods_dir"] == str(custom)
        assert r.json()["resolved_mods_dir"] == str(custom)

    def test_clear_mods_dir(self, client, tmp_path):
        install = tmp_path / "game"
        install.mkdir()
        custom = tmp_path / "staging"
        custom.mkdir()
        client.post(
            "/api/v1/games/",
            json={
                "name": "U2",
                "domain_name": "u",
                "install_path": str(install),
                "mods_dir": str(custom),
            },
        )
        r = client.patch("/api/v1/games/U2", json={"mods_dir": ""})
        assert r.status_code == 200
        assert r.json()["mods_dir"] is None
        # falls back to default
        assert r.json()["resolved_mods_dir"].endswith("downloaded_mods")

    def test_not_found(self, client):
        r = client.patch("/api/v1/games/Nonexistent", json={"mods_dir": "/x"})
        assert r.status_code == 404


class TestValidatePath:
    def test_nonexistent_path(self, client):
        r = client.post(
            "/api/v1/games/validate-path",
            json={"install_path": "/nonexistent/path"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert data["found_exe"] is False
        assert data["found_mod_dirs"] == []
        assert "not found" in data["warning"].lower()

    def test_valid_path_with_exe(self, client, tmp_path):
        # Create a fake Cyberpunk install
        exe_dir = tmp_path / "bin" / "x64"
        exe_dir.mkdir(parents=True)
        (exe_dir / "Cyberpunk2077.exe").touch()

        # Create some mod dirs
        (tmp_path / "mods").mkdir()
        (tmp_path / "archive" / "pc" / "mod").mkdir(parents=True)

        r = client.post(
            "/api/v1/games/validate-path",
            json={"install_path": str(tmp_path)},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["found_exe"] is True
        assert "mods" in data["found_mod_dirs"]
        assert "archive/pc/mod" in data["found_mod_dirs"]

    def test_unknown_domain(self, client):
        r = client.post(
            "/api/v1/games/validate-path",
            json={"install_path": "/some/path", "domain_name": "unknowngame"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert "Unknown game domain" in data["warning"]

    def test_path_without_exe(self, client, tmp_path):
        # Just create a mod dir but no exe
        (tmp_path / "mods").mkdir()

        r = client.post(
            "/api/v1/games/validate-path",
            json={"install_path": str(tmp_path)},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert data["found_exe"] is False


class TestDeleteGame:
    def test_success(self, client):
        client.post(
            "/api/v1/games/",
            json={"name": "ToDelete", "domain_name": "del", "install_path": "/d"},
        )
        r = client.delete("/api/v1/games/ToDelete")
        assert r.status_code == 204

    def test_not_found(self, client):
        r = client.delete("/api/v1/games/NoGame")
        assert r.status_code == 404


def _seed_dependents(session, game_id: int) -> None:
    """Create one row in every table that references ``game_id`` directly or indirectly."""
    from rippermod_manager.models import (
        ActivityLog,
        ArchiveEntryIndex,
        ConflictEvidence,
        DownloadJob,
        InstalledCollection,
        InstalledMod,
        InstalledModFile,
        LoadOrderPreference,
        ModFile,
        ModGroup,
        ModGroupAlias,
        ModNexusCorrelation,
        NexusDownload,
        Profile,
        ProfileEntry,
    )
    from rippermod_manager.models.conflict import ConflictKind, Severity
    from rippermod_manager.models.install import ArchiveNexusLink, DeployJournalEntry

    coll = InstalledCollection(game_id=game_id, slug=f"coll-{game_id}")
    group = ModGroup(game_id=game_id, display_name="Group")
    nd = NexusDownload(game_id=game_id, nexus_mod_id=1)
    session.add_all([coll, group, nd])
    session.flush()
    mod_a = InstalledMod(
        game_id=game_id, name="A", mod_group_id=group.id, installed_collection_id=coll.id
    )
    mod_b = InstalledMod(game_id=game_id, name="B")
    session.add_all([mod_a, mod_b])
    session.flush()
    profile = Profile(game_id=game_id, name="P")
    session.add(profile)
    session.flush()
    session.add_all(
        [
            ProfileEntry(profile_id=profile.id, installed_mod_id=mod_a.id),
            InstalledModFile(installed_mod_id=mod_a.id, relative_path="a.txt"),
            LoadOrderPreference(game_id=game_id, winner_mod_id=mod_a.id, loser_mod_id=mod_b.id),
            ArchiveEntryIndex(
                game_id=game_id,
                installed_mod_id=mod_a.id,
                archive_filename="a.archive",
                resource_hash=1,
            ),
            ConflictEvidence(
                game_id=game_id,
                kind=ConflictKind.archive_resource,
                severity=Severity.high,
                key="k",
            ),
            DownloadJob(
                game_id=game_id,
                nexus_mod_id=1,
                nexus_file_id=2,
                installed_collection_id=coll.id,
            ),
            ModNexusCorrelation(mod_group_id=group.id, nexus_download_id=nd.id),
            ModGroupAlias(mod_group_id=group.id, alias="alias"),
            ModFile(mod_group_id=group.id, file_path=f"/f/{game_id}.txt", filename="f.txt"),
            ArchiveNexusLink(game_id=game_id, filename="a.zip", nexus_mod_id=1),
            DeployJournalEntry(game_id=game_id, operation="link", src="s", dst="d"),
            ActivityLog(game_id=game_id, action="install"),
        ]
    )
    session.commit()


class TestDeleteGameCascade:
    def test_delete_removes_every_dependent_row(self, client, session, make_game):
        from sqlmodel import select

        from rippermod_manager.models import (
            ActivityLog,
            ArchiveEntryIndex,
            ConflictEvidence,
            DownloadJob,
            InstalledCollection,
            InstalledMod,
            InstalledModFile,
            LoadOrderPreference,
            ModFile,
            ModGroup,
            ModGroupAlias,
            ModNexusCorrelation,
            NexusDownload,
            Profile,
            ProfileEntry,
        )
        from rippermod_manager.models.install import ArchiveNexusLink, DeployJournalEntry

        dependent_models = [
            ActivityLog,
            ArchiveEntryIndex,
            ArchiveNexusLink,
            ConflictEvidence,
            DeployJournalEntry,
            DownloadJob,
            InstalledCollection,
            InstalledMod,
            LoadOrderPreference,
            ModGroup,
            NexusDownload,
            Profile,
        ]
        # B first so A holds the highest id and a re-created A reuses it.
        game_b = make_game(name="B")
        game_a = make_game(name="A")
        a_id, b_id = game_a.id, game_b.id
        _seed_dependents(session, a_id)
        session.add(ActivityLog(game_id=b_id, action="install"))
        session.commit()

        assert client.delete("/api/v1/games/A").status_code == 204

        session.expire_all()
        for model in dependent_models:
            assert session.exec(select(model).where(model.game_id == a_id)).all() == [], model
        for model in (
            ModNexusCorrelation,
            ModGroupAlias,
            ModFile,
            InstalledModFile,
            ProfileEntry,
        ):
            assert session.exec(select(model)).all() == [], model
        assert len(session.exec(select(ActivityLog).where(ActivityLog.game_id == b_id)).all()) == 1

        reborn = make_game(name="A")
        assert reborn.id == a_id
        for model in dependent_models:
            assert session.exec(select(model).where(model.game_id == reborn.id)).all() == []
