"""Contract tests for the conflicts router endpoints."""

import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, select

from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def _add_conflicting_mods(engine, game_name: str, paths: list[str]) -> None:
    """Add two mods that share the same files."""
    with Session(engine) as s:
        game = s.exec(select(Game).where(Game.name == game_name)).first()
        mod_a = InstalledMod(game_id=game.id, name="ModA")
        mod_b = InstalledMod(game_id=game.id, name="ModB")
        s.add_all([mod_a, mod_b])
        s.flush()
        for p in paths:
            s.add(InstalledModFile(installed_mod_id=mod_a.id, relative_path=p))
            s.add(InstalledModFile(installed_mod_id=mod_b.id, relative_path=p))
        s.commit()


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def game_setup(tmp_path, client, engine):
    """Create a game via direct DB access — used by engine tests."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    with Session(engine) as s:
        g = Game(name="ConflictsGame", domain_name="cg", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()

    return "ConflictsGame", game_dir


@pytest.fixture
def archive_game_setup(tmp_path, client, engine):
    """Create a game with staging dir — used by archive-comparison tests."""
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    staging = game_dir / "downloaded_mods"
    staging.mkdir()

    with Session(engine) as s:
        g = Game(name="ConflictsGame", domain_name="cg", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="mods"))
        s.commit()
        game_id = g.id

    return "ConflictsGame", game_dir, staging, game_id


# ---------------------------------------------------------------------------
# Persisted engine endpoint tests
# ---------------------------------------------------------------------------


class TestConflictSummary:
    def test_empty_summary(self, client, game_setup):
        game_name, _ = game_setup
        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_conflicts"] == 0
        assert data["game_name"] == "ConflictsGame"
        assert data["evidence"] == []

    def test_game_not_found(self, client):
        r = client.get("/api/v1/games/NoSuchGame/conflicts/summary")
        assert r.status_code == 404

    def test_summary_has_expected_shape(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["overlap.dll"])
        client.post(f"/api/v1/games/{game_name}/conflicts/reindex")

        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_conflicts" in data
        assert "by_severity" in data
        assert "by_kind" in data
        assert isinstance(data["evidence"], list)
        if data["evidence"]:
            ev = data["evidence"][0]
            assert "id" in ev
            assert "kind" in ev
            assert "severity" in ev
            assert "key" in ev
            assert "mods" in ev
            assert isinstance(ev["mods"], list)
            assert "id" in ev["mods"][0]
            assert "name" in ev["mods"][0]

    def test_filter_by_kind(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["shared.txt"])
        client.post(f"/api/v1/games/{game_name}/conflicts/reindex")

        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary?kind=archive_entry")
        assert r.status_code == 200
        data = r.json()
        assert data["total_conflicts"] >= 1

        r2 = client.get(f"/api/v1/games/{game_name}/conflicts/summary?kind=redscript_target")
        assert r2.status_code == 200
        assert r2.json()["total_conflicts"] == 0

    def test_filter_by_severity(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["readme.txt"])
        client.post(f"/api/v1/games/{game_name}/conflicts/reindex")

        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary?severity=low")
        assert r.status_code == 200
        assert r.json()["total_conflicts"] >= 1


class TestReindexConflicts:
    def test_reindex_returns_result(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["same.txt"])

        r = client.post(f"/api/v1/games/{game_name}/conflicts/reindex")
        assert r.status_code == 200
        data = r.json()
        assert data["conflicts_found"] >= 1
        assert "duration_ms" in data
        assert "by_kind" in data

    def test_reindex_game_not_found(self, client):
        r = client.post("/api/v1/games/Missing/conflicts/reindex")
        assert r.status_code == 404

    def test_summary_reflects_reindex(self, client, game_setup, engine):
        game_name, _ = game_setup
        _add_conflicting_mods(engine, game_name, ["overlap.dll"])

        # Before reindex, summary is empty
        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary")
        assert r.json()["total_conflicts"] == 0

        # After reindex, summary has conflicts
        client.post(f"/api/v1/games/{game_name}/conflicts/reindex")
        r = client.get(f"/api/v1/games/{game_name}/conflicts/summary")
        assert r.json()["total_conflicts"] >= 1


class TestArchiveConflictSummaries:
    def test_game_not_found(self, client):
        r = client.get("/api/v1/games/NoSuchGame/conflicts/archive-summaries")
        assert r.status_code == 404

    def test_empty_when_no_conflicts(self, client, game_setup):
        game_name, _ = game_setup
        r = client.get(f"/api/v1/games/{game_name}/conflicts/archive-summaries")
        assert r.status_code == 200
        data = r.json()
        assert data["game_name"] == "ConflictsGame"
        assert data["summaries"] == []
        assert data["total_archives_with_conflicts"] == 0

    def test_returns_summaries_with_mod_names(self, client, game_setup, engine):
        game_name, _ = game_setup

        with Session(engine) as s:
            game = s.exec(select(Game).where(Game.name == game_name)).one()
            mod_a = InstalledMod(game_id=game.id, name="ModAlpha")
            mod_b = InstalledMod(game_id=game.id, name="ModBeta")
            s.add_all([mod_a, mod_b])
            s.flush()

            s.add(
                ArchiveEntryIndex(
                    game_id=game.id,
                    installed_mod_id=mod_a.id,
                    archive_filename="alpha.archive",
                    archive_relative_path="archive/pc/mod/alpha.archive",
                    resource_hash=100,
                    sha1_hex="a" * 40,
                )
            )
            s.add(
                ArchiveEntryIndex(
                    game_id=game.id,
                    installed_mod_id=mod_b.id,
                    archive_filename="beta.archive",
                    archive_relative_path="archive/pc/mod/beta.archive",
                    resource_hash=100,
                    sha1_hex="b" * 40,
                )
            )
            s.commit()

        r = client.get(f"/api/v1/games/{game_name}/conflicts/archive-summaries")
        assert r.status_code == 200
        data = r.json()
        assert data["total_archives_with_conflicts"] == 2
        assert len(data["summaries"]) == 2

        names = {s["archive_filename"]: s for s in data["summaries"]}
        alpha = names["alpha.archive"]
        beta = names["beta.archive"]
        assert alpha["mod_name"] == "ModAlpha"
        assert beta["mod_name"] == "ModBeta"
        assert alpha["winning_entries"] == 1
        assert beta["losing_entries"] == 1
        assert "severity" in alpha
        assert "identical_count" in alpha
        assert "real_count" in alpha


# ---------------------------------------------------------------------------
# On-the-fly archive comparison endpoint tests
# ---------------------------------------------------------------------------


class TestListConflicts:
    def test_empty_no_mods(self, client, archive_game_setup):
        game_name, *_ = archive_game_setup
        r = client.get("/api/v1/conflicts/", params={"game_name": game_name})
        assert r.status_code == 200
        data = r.json()
        assert data["conflict_pairs"] == []
        assert data["total_mods_checked"] == 0

    def test_disjoint_mods_no_conflicts(self, client, archive_game_setup, engine):
        game_name, _, staging, game_id = archive_game_setup
        _install_mod(engine, game_id, "ModA", "ModA.zip", staging, {"mods/a.txt": b"a"})
        _install_mod(engine, game_id, "ModB", "ModB.zip", staging, {"mods/b.txt": b"b"})

        r = client.get("/api/v1/conflicts/", params={"game_name": game_name})
        assert r.status_code == 200
        assert r.json()["conflict_pairs"] == []

    def test_overlapping_mods_detected(self, client, archive_game_setup, engine):
        game_name, _, staging, game_id = archive_game_setup
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

    def test_severity_filter(self, client, archive_game_setup, engine):
        game_name, _, staging, game_id = archive_game_setup
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

    def test_skipped_mods_missing_archive(self, client, archive_game_setup, engine):
        game_name, _, _staging, game_id = archive_game_setup
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

    def test_winner_is_later_install(self, client, archive_game_setup, engine):
        game_name, _, staging, game_id = archive_game_setup
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
    def test_no_overlap(self, client, archive_game_setup, engine):
        game_name, _, staging, game_id = archive_game_setup
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

    def test_overlap_detected(self, client, archive_game_setup, engine):
        game_name, _, staging, game_id = archive_game_setup
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

    def test_mod_not_found(self, client, archive_game_setup):
        game_name, *_ = archive_game_setup
        r = client.get(
            "/api/v1/conflicts/between",
            params={"game_name": game_name, "mod_a": 9999, "mod_b": 9998},
        )
        assert r.status_code == 404

    def test_missing_source_archive_returns_422(self, client, archive_game_setup, engine):
        game_name, _, staging, game_id = archive_game_setup
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

    def test_corrupt_archive_returns_422(self, client, archive_game_setup, engine):
        game_name, _, staging, game_id = archive_game_setup
        id_a = _install_mod(engine, game_id, "ModA", "ModA.zip", staging, {"mods/a.txt": b"a"})
        (staging / "Corrupt.zip").write_bytes(b"not a zip")
        with Session(engine) as s:
            mod_b = InstalledMod(
                game_id=game_id,
                name="CorruptMod",
                source_archive="Corrupt.zip",
            )
            s.add(mod_b)
            s.commit()
            id_b = mod_b.id

        r = client.get(
            "/api/v1/conflicts/between",
            params={"game_name": game_name, "mod_a": id_a, "mod_b": id_b},
        )
        assert r.status_code == 422
        assert "unreadable" in r.json()["detail"].lower()
