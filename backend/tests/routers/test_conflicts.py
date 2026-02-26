import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.fixture
def game_setup(tmp_path, client, engine):
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    staging = game_dir / "downloaded_mods"
    staging.mkdir()

    with Session(engine) as s:
        g = Game(name="ConflictGame", domain_name="cg", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()
        game_id = g.id

    return "ConflictGame", game_dir, staging, game_id


def _install_mod(engine, game_id, name, archive, staging, files, installed_at=None):
    """Helper: create InstalledMod + InstalledModFile rows and a zip archive."""
    archive_path = staging / archive
    _make_zip(archive_path, files)
    with Session(engine) as s:
        mod = InstalledMod(
            game_id=game_id,
            name=name,
            source_archive=archive,
            installed_at=installed_at or datetime.now(UTC),
        )
        s.add(mod)
        s.flush()
        for rel_path in files:
            s.add(InstalledModFile(installed_mod_id=mod.id, relative_path=rel_path.lower()))
        s.commit()
        return mod.id


class TestListConflicts:
    def test_empty_no_mods(self, client, game_setup):
        game_name, *_ = game_setup
        r = client.get("/api/v1/conflicts/", params={"game_name": game_name})
        assert r.status_code == 200
        data = r.json()
        assert data["conflict_pairs"] == []
        assert data["total_mods_checked"] == 0

    def test_disjoint_mods_no_conflicts(self, client, game_setup, engine):
        game_name, _, staging, game_id = game_setup
        _install_mod(engine, game_id, "ModA", "ModA.zip", staging, {"mods/a.txt": b"a"})
        _install_mod(engine, game_id, "ModB", "ModB.zip", staging, {"mods/b.txt": b"b"})

        r = client.get("/api/v1/conflicts/", params={"game_name": game_name})
        assert r.status_code == 200
        assert r.json()["conflict_pairs"] == []

    def test_overlapping_mods_detected(self, client, game_setup, engine):
        game_name, _, staging, game_id = game_setup
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = t1 + timedelta(hours=1)
        _install_mod(
            engine,
            game_id,
            "ModA",
            "ModA.zip",
            staging,
            {"mods/shared.txt": b"a", "mods/a.txt": b"a"},
            installed_at=t1,
        )
        _install_mod(
            engine,
            game_id,
            "ModB",
            "ModB.zip",
            staging,
            {"mods/shared.txt": b"b", "mods/b.txt": b"b"},
            installed_at=t2,
        )

        r = client.get("/api/v1/conflicts/", params={"game_name": game_name})
        assert r.status_code == 200
        data = r.json()
        assert len(data["conflict_pairs"]) == 1
        pair = data["conflict_pairs"][0]
        assert "mods/shared.txt" in pair["conflicting_files"]
        assert pair["severity"] == "low"
        assert pair["winner"] == "ModB"

    def test_severity_filter(self, client, game_setup, engine):
        game_name, _, staging, game_id = game_setup
        # Create overlap with only 1 file (LOW severity)
        _install_mod(engine, game_id, "ModA", "ModA.zip", staging, {"mods/x.txt": b"a"})
        _install_mod(engine, game_id, "ModB", "ModB.zip", staging, {"mods/x.txt": b"b"})

        r = client.get("/api/v1/conflicts/", params={"game_name": game_name, "severity": "high"})
        assert r.status_code == 200
        assert r.json()["conflict_pairs"] == []

        r = client.get("/api/v1/conflicts/", params={"game_name": game_name, "severity": "low"})
        assert r.status_code == 200
        assert len(r.json()["conflict_pairs"]) == 1

    def test_game_not_found(self, client):
        r = client.get("/api/v1/conflicts/", params={"game_name": "NoSuchGame"})
        assert r.status_code == 404

    def test_skipped_mods_missing_archive(self, client, game_setup, engine):
        game_name, _, _staging, game_id = game_setup
        # Create mod with archive file that doesn't exist on disk
        with Session(engine) as s:
            mod = InstalledMod(
                game_id=game_id,
                name="GhostMod",
                source_archive="ghost.zip",
            )
            s.add(mod)
            s.commit()

        r = client.get("/api/v1/conflicts/", params={"game_name": game_name})
        assert r.status_code == 200
        data = r.json()
        assert len(data["skipped_mods"]) == 1
        assert data["skipped_mods"][0]["mod_name"] == "GhostMod"

    def test_winner_is_later_install(self, client, game_setup, engine):
        game_name, _, staging, game_id = game_setup
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        _install_mod(
            engine,
            game_id,
            "Earlier",
            "Earlier.zip",
            staging,
            {"mods/f.txt": b"e"},
            installed_at=t1,
        )
        _install_mod(
            engine,
            game_id,
            "Later",
            "Later.zip",
            staging,
            {"mods/f.txt": b"l"},
            installed_at=t2,
        )

        r = client.get("/api/v1/conflicts/", params={"game_name": game_name})
        pair = r.json()["conflict_pairs"][0]
        assert pair["winner"] == "Later"


class TestBetweenConflicts:
    def test_no_overlap(self, client, game_setup, engine):
        game_name, _, staging, game_id = game_setup
        id_a = _install_mod(engine, game_id, "ModA", "ModA.zip", staging, {"mods/a.txt": b"a"})
        id_b = _install_mod(engine, game_id, "ModB", "ModB.zip", staging, {"mods/b.txt": b"b"})

        r = client.get(
            "/api/v1/conflicts/between",
            params={"game_name": game_name, "mod_a": id_a, "mod_b": id_b},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["conflicting_files"] == []
        assert data["severity"] is None

    def test_overlap_detected(self, client, game_setup, engine):
        game_name, _, staging, game_id = game_setup
        t1 = datetime(2024, 6, 1, tzinfo=UTC)
        t2 = t1 + timedelta(hours=2)
        id_a = _install_mod(
            engine,
            game_id,
            "ModA",
            "ModA.zip",
            staging,
            {"mods/shared.txt": b"a"},
            installed_at=t1,
        )
        id_b = _install_mod(
            engine,
            game_id,
            "ModB",
            "ModB.zip",
            staging,
            {"mods/shared.txt": b"b"},
            installed_at=t2,
        )

        r = client.get(
            "/api/v1/conflicts/between",
            params={"game_name": game_name, "mod_a": id_a, "mod_b": id_b},
        )
        assert r.status_code == 200
        data = r.json()
        assert "mods/shared.txt" in data["conflicting_files"]
        assert data["winner"] == "ModB"

    def test_mod_not_found(self, client, game_setup):
        game_name, *_ = game_setup
        r = client.get(
            "/api/v1/conflicts/between",
            params={"game_name": game_name, "mod_a": 9999, "mod_b": 9998},
        )
        assert r.status_code == 404

    def test_missing_source_archive_returns_422(self, client, game_setup, engine):
        game_name, _, staging, game_id = game_setup
        # mod_a has source_archive, mod_b does not
        id_a = _install_mod(engine, game_id, "ModA", "ModA.zip", staging, {"mods/a.txt": b"a"})
        with Session(engine) as s:
            mod_b = InstalledMod(game_id=game_id, name="NoArchive", source_archive="")
            s.add(mod_b)
            s.commit()
            id_b = mod_b.id

        r = client.get(
            "/api/v1/conflicts/between",
            params={"game_name": game_name, "mod_a": id_a, "mod_b": id_b},
        )
        assert r.status_code == 422
