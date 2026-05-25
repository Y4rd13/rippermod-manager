import os
from pathlib import Path

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import DeployJournalEntry
from rippermod_manager.services.vfs.deploy_service import replay_pending_journal


def _game(session, tmp_path) -> Game:
    g = Game(name="G", domain_name="cyberpunk2077", install_path=str(tmp_path / "game"))
    (tmp_path / "game").mkdir()
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def test_adopt_replay_rolls_forward_when_game_path_missing(session, tmp_path):
    g = _game(session, tmp_path)
    staging = tmp_path / "game" / "downloaded_mods" / "Mod" / "r6" / "tweaks"
    staging.mkdir(parents=True)
    src = staging / "x.tweak"
    src.write_bytes(b"data")  # bytes safe in staging
    dst = Path(g.install_path) / "r6" / "tweaks" / "x.tweak"  # game path missing (crash window)

    session.add(
        DeployJournalEntry(
            game_id=g.id, operation="adopt", src=str(src), dst=str(dst), status="pending"
        )
    )
    session.commit()

    replay_pending_journal(g, session)

    assert dst.exists()  # rolled forward: hardlink recreated from staging
    assert os.path.samefile(src, dst)  # same inode
    entry = session.query(DeployJournalEntry).first()
    assert entry.status == "done"


def test_adopt_replay_noop_when_already_linked(session, tmp_path):
    g = _game(session, tmp_path)
    staging = tmp_path / "game" / "downloaded_mods" / "Mod"
    staging.mkdir(parents=True)
    src = staging / "a.archive"
    src.write_bytes(b"d")
    dst = Path(g.install_path) / "a.archive"
    os.link(src, dst)  # already linked

    session.add(
        DeployJournalEntry(
            game_id=g.id, operation="adopt", src=str(src), dst=str(dst), status="pending"
        )
    )
    session.commit()

    replay_pending_journal(g, session)  # must not raise, must not delete anything
    assert dst.exists()
    assert src.exists()
