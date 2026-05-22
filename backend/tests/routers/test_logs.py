"""Tests for the mod error reader endpoint."""


class TestLogsRouter:
    def test_returns_parsed_errors(self, client, make_game, tmp_path):
        make_game(name="CP", install_path=str(tmp_path))
        log = tmp_path / "red4ext" / "logs" / "red4ext-1.log"
        log.parent.mkdir(parents=True)
        log.write_text(
            "[2026-05-18 18:22:48.000] [RED4ext] [error] plugin X failed\n"
            "[2026-05-18 18:22:49.000] [RED4ext] [info] all good\n",
            encoding="utf-8",
        )
        resp = client.get("/api/v1/games/CP/log-errors/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1  # info dropped
        assert data[0]["source"] == "RED4ext"
        assert data[0]["level"] == "error"
        assert data[0]["message"] == "plugin X failed"
        assert data[0]["mod_name"] is None

    def test_empty_when_no_logs(self, client, make_game, tmp_path):
        make_game(name="CP", install_path=str(tmp_path))
        resp = client.get("/api/v1/games/CP/log-errors/")
        assert resp.status_code == 200
        assert resp.json() == []
