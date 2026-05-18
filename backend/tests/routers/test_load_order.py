from datetime import UTC, datetime

import pytest
from sqlmodel import Session, select

from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind, Severity
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.models.load_order import LoadOrderPreference


@pytest.fixture
def game_setup(tmp_path, client, engine):
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "archive" / "pc" / "mod").mkdir(parents=True)

    with Session(engine) as s:
        g = Game(name="LoadOrderGame", domain_name="cyberpunk2077", install_path=str(game_dir))
        s.add(g)
        s.flush()
        s.add(GameModPath(game_id=g.id, relative_path="archive/pc/mod"))
        s.commit()

    return "LoadOrderGame", game_dir


def _add_mod(engine, game_name, mod_name, archive_filenames, *, game_dir=None, disabled=False):
    """Insert an InstalledMod with archive files via a fresh session."""
    with Session(engine) as s:
        g = s.exec(select(Game).where(Game.name == game_name)).one()
        mod = InstalledMod(
            game_id=g.id,
            name=mod_name,
            disabled=disabled,
            installed_at=datetime.now(UTC),
        )
        s.add(mod)
        s.flush()
        for fn in archive_filenames:
            rel = f"archive/pc/mod/{fn}"
            s.add(InstalledModFile(installed_mod_id=mod.id, relative_path=rel))
            if game_dir is not None:
                fp = game_dir / "archive" / "pc" / "mod" / fn
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(b"data")
        s.commit()
        s.refresh(mod)
        return mod.id


class TestLoadOrderEndpoint:
    def test_404_for_unknown_game(self, client):
        r = client.get("/api/v1/games/NoSuchGame/load-order/")
        assert r.status_code == 404

    def test_empty_load_order(self, client, game_setup):
        game_name, _ = game_setup
        r = client.get(f"/api/v1/games/{game_name}/load-order/")
        assert r.status_code == 200
        data = r.json()
        assert data["total_archives"] == 0
        assert data["load_order"] == []
        assert data["conflicts"] == []

    def test_returns_sorted_entries(self, client, engine, game_setup):
        game_name, _ = game_setup
        _add_mod(engine, game_name, "ModZ", ["zzz.archive"])
        _add_mod(engine, game_name, "ModA", ["aaa.archive"])

        r = client.get(f"/api/v1/games/{game_name}/load-order/")
        assert r.status_code == 200
        data = r.json()
        assert data["total_archives"] == 2
        filenames = [e["archive_filename"] for e in data["load_order"]]
        assert filenames == ["aaa.archive", "zzz.archive"]


class TestPreferPreviewEndpoint:
    def test_404_for_unknown_game(self, client):
        r = client.post(
            "/api/v1/games/NoSuchGame/load-order/prefer/preview",
            json={"winner_mod_id": 1, "loser_mod_ids": [2]},
        )
        assert r.status_code == 404

    def test_returns_dry_run_true(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        w_id = _add_mod(engine, game_name, "Winner", ["aaa.archive"], game_dir=game_dir)
        l_id = _add_mod(engine, game_name, "Loser", ["bbb.archive"], game_dir=game_dir)

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer/preview",
            json={"winner_mod_id": w_id, "loser_mod_ids": [l_id]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["dry_run"] is True
        assert data["success"] is True

    def test_unknown_mod_id_returns_404(self, client, engine, game_setup):
        game_name, _ = game_setup
        w_id = _add_mod(engine, game_name, "Winner", ["aaa.archive"])

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer/preview",
            json={"winner_mod_id": w_id, "loser_mod_ids": [99999]},
        )
        assert r.status_code == 404

    def test_same_mod_id_returns_400(self, client, engine, game_setup):
        game_name, _ = game_setup
        w_id = _add_mod(engine, game_name, "SomeMod", ["aaa.archive"])

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer/preview",
            json={"winner_mod_id": w_id, "loser_mod_ids": [w_id]},
        )
        assert r.status_code == 400

    def test_disabled_mod_returns_400(self, client, engine, game_setup):
        game_name, _ = game_setup
        w_id = _add_mod(engine, game_name, "Winner", ["aaa.archive"])
        l_id = _add_mod(engine, game_name, "Loser", ["bbb.archive"], disabled=True)

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer/preview",
            json={"winner_mod_id": w_id, "loser_mod_ids": [l_id]},
        )
        assert r.status_code == 400


class TestPreferEndpoint:
    def test_404_for_unknown_game(self, client):
        r = client.post(
            "/api/v1/games/NoSuchGame/load-order/prefer",
            json={"winner_mod_id": 1, "loser_mod_ids": [2]},
        )
        assert r.status_code == 404

    def test_adds_preference_and_writes_modlist(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        w_id = _add_mod(engine, game_name, "Winner", ["bbb.archive"], game_dir=game_dir)
        l_id = _add_mod(engine, game_name, "Loser", ["aaa.archive"], game_dir=game_dir)

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer",
            json={"winner_mod_id": w_id, "loser_mod_ids": [l_id]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["dry_run"] is False
        assert data["preferences_added"] == 1
        # modlist.txt should be written
        modlist_path = game_dir / "archive" / "pc" / "mod" / "modlist.txt"
        assert modlist_path.exists()
        lines = modlist_path.read_text().strip().splitlines()
        assert lines[0] == "bbb.archive"
        assert lines[1] == "aaa.archive"


class TestBatchPreferencesEndpoint:
    def test_404_for_unknown_game(self, client):
        r = client.post(
            "/api/v1/games/NoSuchGame/load-order/preferences/batch",
            json={"add": [], "remove": []},
        )
        assert r.status_code == 404

    def test_no_op_when_empty(self, client, game_setup):
        game_name, _ = game_setup
        r = client.post(
            f"/api/v1/games/{game_name}/load-order/preferences/batch",
            json={"add": [], "remove": []},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["added"] == 0
        assert data["removed"] == 0

    def test_add_pairs(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        a = _add_mod(engine, game_name, "ModA", ["a.archive"], game_dir=game_dir)
        b = _add_mod(engine, game_name, "ModB", ["b.archive"], game_dir=game_dir)
        r = client.post(
            f"/api/v1/games/{game_name}/load-order/preferences/batch",
            json={
                "add": [{"winner_mod_id": b, "loser_mod_id": a}],
                "remove": [],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["added"] == 1
        assert data["removed"] == 0
        modlist_path = game_dir / "archive" / "pc" / "mod" / "modlist.txt"
        assert modlist_path.exists()
        lines = modlist_path.read_text().strip().splitlines()
        assert lines[0] == "b.archive"

    def test_remove_pair(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        a = _add_mod(engine, game_name, "ModA", ["a.archive"], game_dir=game_dir)
        b = _add_mod(engine, game_name, "ModB", ["b.archive"], game_dir=game_dir)
        client.post(
            f"/api/v1/games/{game_name}/load-order/preferences/batch",
            json={"add": [{"winner_mod_id": b, "loser_mod_id": a}], "remove": []},
        )
        r = client.post(
            f"/api/v1/games/{game_name}/load-order/preferences/batch",
            json={
                "add": [],
                "remove": [{"winner_mod_id": b, "loser_mod_id": a}],
            },
        )
        assert r.status_code == 200
        assert r.json()["removed"] == 1

    def test_flip_pair_in_one_call(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        a = _add_mod(engine, game_name, "ModA", ["a.archive"], game_dir=game_dir)
        b = _add_mod(engine, game_name, "ModB", ["b.archive"], game_dir=game_dir)
        client.post(
            f"/api/v1/games/{game_name}/load-order/preferences/batch",
            json={"add": [{"winner_mod_id": a, "loser_mod_id": b}], "remove": []},
        )
        r = client.post(
            f"/api/v1/games/{game_name}/load-order/preferences/batch",
            json={
                "add": [{"winner_mod_id": b, "loser_mod_id": a}],
                "remove": [{"winner_mod_id": a, "loser_mod_id": b}],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["added"] == 1
        assert data["removed"] == 1

    def test_idempotent_add(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        a = _add_mod(engine, game_name, "ModA", ["a.archive"], game_dir=game_dir)
        b = _add_mod(engine, game_name, "ModB", ["b.archive"], game_dir=game_dir)
        body = {"add": [{"winner_mod_id": b, "loser_mod_id": a}], "remove": []}
        client.post(f"/api/v1/games/{game_name}/load-order/preferences/batch", json=body)
        r = client.post(f"/api/v1/games/{game_name}/load-order/preferences/batch", json=body)
        assert r.status_code == 200
        assert r.json()["added"] == 0

    def test_unknown_mod_id_returns_404(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        a = _add_mod(engine, game_name, "ModA", ["a.archive"], game_dir=game_dir)
        r = client.post(
            f"/api/v1/games/{game_name}/load-order/preferences/batch",
            json={
                "add": [{"winner_mod_id": a, "loser_mod_id": 99999}],
                "remove": [],
            },
        )
        assert r.status_code == 404


class TestAutoSortEndpoints:
    def _seed_conflict(self, engine, game_id, mod_a, mod_b):
        with Session(engine) as s:
            s.add(
                ConflictEvidence(
                    game_id=game_id,
                    kind=ConflictKind.archive_resource,
                    severity=Severity.medium,
                    key="resource:abc",
                    mod_ids=f"{mod_a},{mod_b}",
                    winner_mod_id=mod_a,
                )
            )
            s.commit()

    def _game_id(self, engine, game_name):
        with Session(engine) as s:
            g = s.exec(select(Game).where(Game.name == game_name)).one()
            return g.id

    def test_preview_no_conflicts(self, client, game_setup):
        game_name, _ = game_setup
        r = client.post(f"/api/v1/games/{game_name}/load-order/auto-sort/preview")
        assert r.status_code == 200
        data = r.json()
        assert data["proposed_add"] == []
        assert data["proposed_remove"] == []
        assert data["conflict_pairs_evaluated"] == 0

    def test_preview_smaller_mod_wins(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        small = _add_mod(engine, game_name, "Small", ["s.archive"], game_dir=game_dir)
        big = _add_mod(
            engine,
            game_name,
            "Big",
            ["b1.archive", "b2.archive", "b3.archive"],
            game_dir=game_dir,
        )
        self._seed_conflict(engine, self._game_id(engine, game_name), small, big)

        r = client.post(f"/api/v1/games/{game_name}/load-order/auto-sort/preview")
        assert r.status_code == 200
        data = r.json()
        assert len(data["proposed_add"]) == 1
        prop = data["proposed_add"][0]
        assert prop["winner_mod_id"] == small
        assert prop["loser_mod_id"] == big
        assert data["conflict_pairs_evaluated"] == 1

    def test_preview_skips_ties(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        a = _add_mod(engine, game_name, "ModA", ["a.archive"], game_dir=game_dir)
        b = _add_mod(engine, game_name, "ModB", ["b.archive"], game_dir=game_dir)
        self._seed_conflict(engine, self._game_id(engine, game_name), a, b)

        r = client.post(f"/api/v1/games/{game_name}/load-order/auto-sort/preview")
        data = r.json()
        assert data["proposed_add"] == []
        assert data["conflict_pairs_evaluated"] == 0

    def test_preview_proposes_remove_of_opposite(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        small = _add_mod(engine, game_name, "Small", ["s.archive"], game_dir=game_dir)
        big = _add_mod(
            engine,
            game_name,
            "Big",
            ["b1.archive", "b2.archive"],
            game_dir=game_dir,
        )
        self._seed_conflict(engine, self._game_id(engine, game_name), small, big)
        with Session(engine) as s:
            s.add(
                LoadOrderPreference(
                    game_id=self._game_id(engine, game_name),
                    winner_mod_id=big,
                    loser_mod_id=small,
                )
            )
            s.commit()

        r = client.post(f"/api/v1/games/{game_name}/load-order/auto-sort/preview")
        data = r.json()
        assert len(data["proposed_add"]) == 1
        assert len(data["proposed_remove"]) == 1
        assert data["proposed_remove"][0]["winner_mod_id"] == big
        assert data["proposed_remove"][0]["loser_mod_id"] == small

    def test_apply_writes_modlist(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        small = _add_mod(engine, game_name, "Small", ["s.archive"], game_dir=game_dir)
        big = _add_mod(
            engine,
            game_name,
            "Big",
            ["b1.archive", "b2.archive"],
            game_dir=game_dir,
        )
        self._seed_conflict(engine, self._game_id(engine, game_name), small, big)

        r = client.post(f"/api/v1/games/{game_name}/load-order/auto-sort/apply")
        assert r.status_code == 200
        data = r.json()
        assert data["added"] == 1
        modlist_path = game_dir / "archive" / "pc" / "mod" / "modlist.txt"
        assert modlist_path.exists()
        first_line = modlist_path.read_text().strip().splitlines()[0]
        assert first_line == "s.archive"

    def test_apply_no_conflicts_is_noop(self, client, game_setup):
        game_name, _ = game_setup
        r = client.post(f"/api/v1/games/{game_name}/load-order/auto-sort/apply")
        assert r.status_code == 200
        data = r.json()
        assert data["added"] == 0
        assert data["removed"] == 0
