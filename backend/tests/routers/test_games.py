from pathlib import Path

import pytest

CP = "cyberpunk2077"


def _cp_dir(tmp_path: Path, name: str = "game") -> str:
    """Create a fake Cyberpunk 2077 install (with its exe) under *tmp_path*."""
    root = tmp_path / name
    (root / "bin" / "x64").mkdir(parents=True, exist_ok=True)
    (root / "bin" / "x64" / "Cyberpunk2077.exe").write_bytes(b"MZ")
    return str(root)


def _create(client, name: str, install_path: str, **extra):
    return client.post(
        "/api/v1/games/",
        json={"name": name, "domain_name": CP, "install_path": install_path, **extra},
    )


class TestListGames:
    def test_empty(self, client):
        r = client.get("/api/v1/games/")
        assert r.status_code == 200
        assert r.json() == []


class TestCreateGame:
    def test_success(self, client, tmp_path):
        r = _create(client, "TestGame", _cp_dir(tmp_path))
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "TestGame"
        assert data["domain_name"] == CP

    def test_auto_cyberpunk_paths(self, client, tmp_path):
        r = _create(client, "Cyberpunk 2077", _cp_dir(tmp_path))
        assert r.status_code == 201
        paths = r.json()["mod_paths"]
        assert len(paths) == 10
        rels = {p["relative_path"] for p in paths}
        assert {"archive/pc/patch", "r6/config"} <= rels

    def test_custom_paths(self, client, tmp_path):
        r = _create(
            client,
            "Custom",
            _cp_dir(tmp_path),
            mod_paths=[{"relative_path": "mods", "description": "Main"}],
        )
        assert r.status_code == 201
        assert len(r.json()["mod_paths"]) == 1

    @pytest.mark.parametrize("path", [r"\\server\share\Cyberpunk 2077", "//server/share/cp"])
    def test_unc_install_path_is_422(self, client, path):
        r = _create(client, "Unc", path)
        assert r.status_code == 422
        assert client.get("/api/v1/games/").json() == []

    def test_install_path_without_exe_is_422(self, client, tmp_path):
        (tmp_path / "System32").mkdir()
        r = _create(client, "NoExe", str(tmp_path / "System32"))
        assert r.status_code == 422
        assert "Cyberpunk2077.exe" in r.json()["detail"]
        assert client.get("/api/v1/games/").json() == []

    def test_unregistered_domain_is_422(self, client, tmp_path):
        r = client.post(
            "/api/v1/games/",
            json={"name": "G1", "domain_name": "g1", "install_path": _cp_dir(tmp_path)},
        )
        assert r.status_code == 422
        assert client.get("/api/v1/games/").json() == []

    def test_duplicate_name_is_409(self, client, tmp_path):
        first = _cp_dir(tmp_path, "first")
        assert _create(client, "DupGame", first).status_code == 201
        r = _create(client, "DupGame", _cp_dir(tmp_path, "second"))
        assert r.status_code == 409
        assert client.get("/api/v1/games/DupGame").json()["install_path"] == first


class TestGetGame:
    def test_found(self, client, tmp_path):
        _create(client, "G1", _cp_dir(tmp_path))
        r = client.get("/api/v1/games/G1")
        assert r.status_code == 200
        assert r.json()["name"] == "G1"

    def test_not_found(self, client):
        r = client.get("/api/v1/games/Nonexistent")
        assert r.status_code == 404

    def test_resolved_mods_dir_default(self, client, tmp_path):
        install = _cp_dir(tmp_path)
        _create(client, "DefDir", install)
        r = client.get("/api/v1/games/DefDir")
        assert r.status_code == 200
        data = r.json()
        assert data["mods_dir"] is None
        assert data["resolved_mods_dir"] == str(Path(install) / "downloaded_mods")

    def test_resolved_mods_dir_with_override(self, client, tmp_path):
        custom = tmp_path / "staging"
        custom.mkdir()
        _create(client, "OvrDir", _cp_dir(tmp_path), mods_dir=str(custom))
        r = client.get("/api/v1/games/OvrDir")
        assert r.status_code == 200
        data = r.json()
        assert data["mods_dir"] == str(custom)
        assert data["resolved_mods_dir"] == str(custom)

    def test_post_rejects_cross_volume_mods_dir(self, client, monkeypatch, tmp_path):
        # Force same_volume to return False so this works regardless of test env layout.
        from rippermod_manager.routers import games as games_router

        monkeypatch.setattr(games_router, "same_volume", lambda a, b: False)
        bad_mods_dir = tmp_path / "bad"
        bad_mods_dir.mkdir()
        r = _create(client, "CrossVol", _cp_dir(tmp_path), mods_dir=str(bad_mods_dir))
        assert r.status_code == 422, r.text
        assert "same physical volume" in r.json()["detail"]

    def test_post_accepts_same_volume_mods_dir(self, client, tmp_path):
        custom = tmp_path / "staging"
        custom.mkdir()
        r = _create(client, "SameVol", _cp_dir(tmp_path), mods_dir=str(custom))
        assert r.status_code == 201, r.text
        assert r.json()["mods_dir"] == str(custom)
        assert r.json()["resolved_mods_dir"] == str(custom)


class TestUpdateGame:
    def test_set_mods_dir_same_volume(self, client, tmp_path):
        custom = tmp_path / "staging"
        custom.mkdir()
        _create(client, "U1", _cp_dir(tmp_path))
        r = client.patch("/api/v1/games/U1", json={"mods_dir": str(custom)})
        assert r.status_code == 200, r.text
        assert r.json()["mods_dir"] == str(custom)
        assert r.json()["resolved_mods_dir"] == str(custom)

    def test_clear_mods_dir(self, client, tmp_path):
        custom = tmp_path / "staging"
        custom.mkdir()
        _create(client, "U2", _cp_dir(tmp_path), mods_dir=str(custom))
        r = client.patch("/api/v1/games/U2", json={"mods_dir": ""})
        assert r.status_code == 200
        assert r.json()["mods_dir"] is None
        # falls back to default
        assert r.json()["resolved_mods_dir"].endswith("downloaded_mods")

    def test_not_found(self, client):
        r = client.patch("/api/v1/games/Nonexistent", json={"mods_dir": "/x"})
        assert r.status_code == 404

    def test_patch_install_path_valid(self, client, tmp_path):
        _create(client, "U3", _cp_dir(tmp_path, "old"))
        new = _cp_dir(tmp_path, "new")
        r = client.patch("/api/v1/games/U3", json={"install_path": new})
        assert r.status_code == 200, r.text
        assert r.json()["install_path"] == new

    @pytest.mark.parametrize("bad", ["//server/share/cp", "missing-exe"])
    def test_patch_install_path_invalid_keeps_old(self, client, tmp_path, bad):
        old = _cp_dir(tmp_path, "old")
        _create(client, "U4", old)
        if bad == "missing-exe":
            (tmp_path / "empty").mkdir()
            bad = str(tmp_path / "empty")
        r = client.patch("/api/v1/games/U4", json={"install_path": bad})
        assert r.status_code == 422
        assert client.get("/api/v1/games/U4").json()["install_path"] == old

    def test_patch_install_path_revalidates_mods_dir(self, client, tmp_path, monkeypatch):
        from rippermod_manager.routers import games as games_router

        custom = tmp_path / "staging"
        custom.mkdir()
        old = _cp_dir(tmp_path, "old")
        _create(client, "U5", old, mods_dir=str(custom))
        monkeypatch.setattr(games_router, "same_volume", lambda a, b: False)
        r = client.patch("/api/v1/games/U5", json={"install_path": _cp_dir(tmp_path, "new")})
        assert r.status_code == 422
        assert client.get("/api/v1/games/U5").json()["install_path"] == old


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
    def test_success(self, client, tmp_path):
        _create(client, "ToDelete", _cp_dir(tmp_path))
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
    from rippermod_manager.models.install import (
        ArchiveNexusLink,
        DeployJournalEntry,
        DisplacedFile,
    )

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
            DisplacedFile(
                game_id=game_id,
                relative_path="r6/config/x.xml",
                backup_path="/b/x.xml",
                occupant_mod_id=mod_a.id,
            ),
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
        from rippermod_manager.models.install import (
            ArchiveNexusLink,
            DeployJournalEntry,
            DisplacedFile,
        )

        dependent_models = [
            ActivityLog,
            DisplacedFile,
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

        session.expunge_all()  # drop the deleted Game A from the identity map
        reborn = make_game(name="A")
        assert reborn.id == a_id
        for model in dependent_models:
            assert session.exec(select(model).where(model.game_id == reborn.id)).all() == []
