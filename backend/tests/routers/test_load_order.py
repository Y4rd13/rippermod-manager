from datetime import UTC, datetime

import pytest
from sqlmodel import Session, select

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile


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
            json={"winner_mod_id": 1, "loser_mod_id": 2},
        )
        assert r.status_code == 404

    def test_returns_dry_run_true(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        w_id = _add_mod(engine, game_name, "Winner", ["aaa.archive"], game_dir=game_dir)
        l_id = _add_mod(engine, game_name, "Loser", ["bbb.archive"], game_dir=game_dir)

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer/preview",
            json={"winner_mod_id": w_id, "loser_mod_id": l_id},
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
            json={"winner_mod_id": w_id, "loser_mod_id": 99999},
        )
        assert r.status_code == 404

    def test_same_mod_id_returns_400(self, client, engine, game_setup):
        game_name, _ = game_setup
        w_id = _add_mod(engine, game_name, "SomeMod", ["aaa.archive"])

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer/preview",
            json={"winner_mod_id": w_id, "loser_mod_id": w_id},
        )
        assert r.status_code == 400

    def test_disabled_mod_returns_400(self, client, engine, game_setup):
        game_name, _ = game_setup
        w_id = _add_mod(engine, game_name, "Winner", ["aaa.archive"])
        l_id = _add_mod(engine, game_name, "Loser", ["bbb.archive"], disabled=True)

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer/preview",
            json={"winner_mod_id": w_id, "loser_mod_id": l_id},
        )
        assert r.status_code == 400


class TestPreferEndpoint:
    def test_404_for_unknown_game(self, client):
        r = client.post(
            "/api/v1/games/NoSuchGame/load-order/prefer",
            json={"winner_mod_id": 1, "loser_mod_id": 2},
        )
        assert r.status_code == 404

    def test_executes_rename(self, client, engine, game_setup):
        game_name, game_dir = game_setup
        w_id = _add_mod(engine, game_name, "Winner", ["bbb.archive"], game_dir=game_dir)
        l_id = _add_mod(engine, game_name, "Loser", ["aaa.archive"], game_dir=game_dir)

        r = client.post(
            f"/api/v1/games/{game_name}/load-order/prefer",
            json={"winner_mod_id": w_id, "loser_mod_id": l_id},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["dry_run"] is False
        assert len(data["renames"]) == 1
        # Verify loser's file was renamed on disk (demoted)
        assert not (game_dir / "archive" / "pc" / "mod" / "aaa.archive").exists()
        assert (game_dir / "archive" / "pc" / "mod" / "zz_aaa.archive").exists()
        # Winner's file should be untouched
        assert (game_dir / "archive" / "pc" / "mod" / "bbb.archive").exists()
