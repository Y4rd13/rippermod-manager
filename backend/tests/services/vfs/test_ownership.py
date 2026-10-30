"""Per-path win order (S4): who owns a destination path when several mods ship it."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.paths import get_mods_dir
from rippermod_manager.services.vfs.ownership import (
    backfill_win_seq,
    next_win_seq,
    path_key,
    winner_map,
)
from rippermod_manager.services.vfs.primitives import hardlink

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _mod(session, game, name, *, files, win_seq=0, age_days=0, disabled=False, stage=True):
    """Create an InstalledMod with ``files`` (relative paths) staged under its own dir."""
    mod = InstalledMod(
        game_id=game.id,
        name=name,
        staging_dir=name,
        disabled=disabled,
        installed_at=T0 + timedelta(days=age_days),
    )
    session.add(mod)
    session.flush()
    for rel in files:
        kind = "junction" if rel.startswith("mods/") and rel.count("/") >= 2 else "hardlink"
        session.add(
            InstalledModFile(
                installed_mod_id=mod.id,
                relative_path=rel,
                source_path=rel,
                link_kind=kind,
                win_seq=win_seq,
            )
        )
        if stage:
            src = get_mods_dir(game) / name / rel
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(f"from {name}".encode())
    session.commit()
    session.refresh(mod)
    return mod


class TestPathKey:
    def test_hardlink_key_is_lowercase_forward_slash(self):
        assert path_key("R6\\Scripts\\A.reds", "hardlink") == "r6/scripts/a.reds"

    def test_junction_key_is_the_redmod_root(self):
        assert path_key("mods/MyMod/info.json", "junction") == "mods/mymod"


class TestWinnerMap:
    def test_highest_enabled_win_seq_wins(self, in_memory_session, sample_game):
        s, g = in_memory_session, sample_game
        _mod(s, g, "A", files=["shared.txt"], win_seq=1)
        _mod(s, g, "B", files=["Shared.TXT"], win_seq=2)
        _mod(s, g, "C", files=["shared.txt"], win_seq=3, disabled=True)

        assert winner_map(s, g.id)["shared.txt"][0].name == "B"

    def test_next_win_seq_is_above_every_existing_row(self, in_memory_session, sample_game):
        s, g = in_memory_session, sample_game
        assert next_win_seq(s, g.id) == 1
        _mod(s, g, "A", files=["a.txt"], win_seq=4)
        assert next_win_seq(s, g.id) == 5


class TestInstallAssignsWinSeq:
    def test_later_install_gets_higher_win_seq(self, session, tmp_path):
        import zipfile

        from sqlmodel import select

        from rippermod_manager.models.game import Game, GameModPath
        from rippermod_manager.services.install_service import install_mod

        game_dir = tmp_path / "game"
        staging = game_dir / "downloaded_mods"
        staging.mkdir(parents=True)
        game = Game(name="G", domain_name="g", install_path=str(game_dir))
        session.add(game)
        session.flush()
        session.add(GameModPath(game_id=game.id, relative_path="mods"))
        session.commit()
        for name in ("A", "B"):
            with zipfile.ZipFile(staging / f"{name}.zip", "w") as zf:
                zf.writestr("shared.txt", name)
        install_mod(game, staging / "A.zip", session, skip_conflicts=[])
        install_mod(game, staging / "B.zip", session, skip_conflicts=[])

        rows = {
            m.name: f.win_seq
            for m, f in session.exec(
                select(InstalledMod, InstalledModFile).where(
                    InstalledModFile.installed_mod_id == InstalledMod.id
                )
            ).all()
        }
        assert 0 < rows["A"] < rows["B"]


class TestBackfill:
    def test_backfill_gives_win_to_current_hardlink_holder(self, in_memory_session, sample_game):
        s, g = in_memory_session, sample_game
        _mod(s, g, "A", files=["shared.txt"], age_days=0)
        b = _mod(s, g, "B", files=["shared.txt"], age_days=1)
        hardlink(
            get_mods_dir(g) / b.staging_dir / "shared.txt", Path(g.install_path) / "shared.txt"
        )

        backfill_win_seq(g, s)

        assert winner_map(s, g.id)["shared.txt"][0].name == "B"

    def test_backfill_falls_back_to_oldest_installed_at(self, in_memory_session, sample_game):
        s, g = in_memory_session, sample_game
        _mod(s, g, "B", files=["shared.txt"], age_days=1)
        _mod(s, g, "A", files=["shared.txt"], age_days=0)

        assert backfill_win_seq(g, s) == 2
        assert winner_map(s, g.id)["shared.txt"][0].name == "A"

    def test_second_backfill_changes_nothing(self, in_memory_session, sample_game):
        s, g = in_memory_session, sample_game
        _mod(s, g, "A", files=["shared.txt", "a.txt"])
        _mod(s, g, "B", files=["shared.txt"], age_days=1)

        assert backfill_win_seq(g, s) == 3
        assert backfill_win_seq(g, s) == 0
