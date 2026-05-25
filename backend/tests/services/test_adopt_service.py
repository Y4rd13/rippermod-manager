import os
from pathlib import Path

import pytest
from sqlmodel import select

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.install_service import adopt_mod, toggle_mod, uninstall_mod


@pytest.fixture
def game(session, tmp_path):
    d = tmp_path / "game"
    d.mkdir()
    g = Game(name="CP", domain_name="cyberpunk2077", install_path=str(d))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="archive/pc/mod"))
    session.commit()
    session.refresh(g)
    return g


def _put(game: Game, rel: str, data: bytes = b"x") -> Path:
    p = Path(game.install_path) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_adopt_moves_to_staging_and_hardlinks_back(session, game):
    _put(game, "archive/pc/mod/cool.archive", b"COOL")

    result = adopt_mod(game, "Cool Mod", ["archive/pc/mod/cool.archive"], session)

    assert result.name == "Cool Mod"
    assert result.files_extracted == 1
    game_path = Path(game.install_path) / "archive/pc/mod/cool.archive"
    staging_path = (
        Path(game.install_path)
        / "downloaded_mods"
        / result.installed_mod_name_safe
        / "archive/pc/mod/cool.archive"
    )
    assert game_path.exists() and staging_path.exists()
    assert os.path.samefile(game_path, staging_path)  # hardlink, same inode
    assert game_path.read_bytes() == b"COOL"  # content preserved


def test_adopt_creates_installed_mod_with_empty_source_archive(session, game):
    _put(game, "archive/pc/mod/m.archive")
    result = adopt_mod(game, "M", ["archive/pc/mod/m.archive"], session)
    mod = session.get(InstalledMod, result.installed_mod_id)
    assert mod.source_archive == ""
    assert mod.disabled is False
    assert mod.staging_dir == result.installed_mod_name_safe
    files = session.exec(
        select(InstalledModFile).where(InstalledModFile.installed_mod_id == mod.id)
    ).all()
    assert len(files) == 1
    assert files[0].relative_path == "archive/pc/mod/m.archive"
    assert files[0].source_path == "archive/pc/mod/m.archive"
    assert files[0].link_kind == "hardlink"


def test_adopt_attaches_nexus_mod_id(session, game):
    _put(game, "archive/pc/mod/x.archive")
    result = adopt_mod(game, "X", ["archive/pc/mod/x.archive"], session, nexus_mod_id=4198)
    mod = session.get(InstalledMod, result.installed_mod_id)
    assert mod.nexus_mod_id == 4198


def test_adopt_rejects_duplicate_name(session, game):
    _put(game, "archive/pc/mod/a.archive")
    adopt_mod(game, "Dup", ["archive/pc/mod/a.archive"], session)
    _put(game, "archive/pc/mod/b.archive")
    with pytest.raises(ValueError, match="already installed"):
        adopt_mod(game, "Dup", ["archive/pc/mod/b.archive"], session)


def test_adopted_mod_disable_enable_round_trip(session, game):
    _put(game, "archive/pc/mod/t.archive", b"T")
    result = adopt_mod(game, "T", ["archive/pc/mod/t.archive"], session)
    mod = session.get(InstalledMod, result.installed_mod_id)
    game_path = Path(game.install_path) / "archive/pc/mod/t.archive"

    toggle_mod(mod, game, session)  # disable -> game-dir link removed, staging kept
    assert not game_path.exists()
    session.refresh(mod)
    assert mod.disabled is True

    toggle_mod(mod, game, session)  # enable -> relinked from staging
    assert game_path.exists()
    assert game_path.read_bytes() == b"T"


def test_uninstall_adopted_mod_removes_both_copies(session, game):
    _put(game, "archive/pc/mod/u.archive")
    result = adopt_mod(game, "U", ["archive/pc/mod/u.archive"], session)
    mod = session.get(InstalledMod, result.installed_mod_id)
    safe = result.installed_mod_name_safe

    uninstall_mod(mod, game, session)

    assert not (Path(game.install_path) / "archive/pc/mod/u.archive").exists()
    assert not (Path(game.install_path) / "downloaded_mods" / safe).exists()


def test_adopt_skips_missing_or_nonfile_paths(session, game):
    _put(game, "archive/pc/mod/real.archive")
    result = adopt_mod(
        game, "Mixed", ["archive/pc/mod/real.archive", "archive/pc/mod/ghost.archive"], session
    )
    assert result.files_extracted == 1
    assert result.files_skipped == 1


def test_adopted_files_report_as_linked_not_foreign(session, game):
    from rippermod_manager.services.vfs.deploy_service import detect_drift

    _put(game, "archive/pc/mod/d1.archive")
    _put(game, "r6/tweaks/d2.tweak")
    adopt_mod(game, "DriftMod", ["archive/pc/mod/d1.archive", "r6/tweaks/d2.tweak"], session)

    report = detect_drift(game, session)
    assert report.total == 2
    assert report.linked == 2
    assert report.foreign == 0
    assert report.missing == 0


def test_adopt_rolls_back_all_files_and_marks_journal_failed_on_failure(session, game, monkeypatch):
    from rippermod_manager.models.install import DeployJournalEntry
    from rippermod_manager.services import install_service

    _put(game, "archive/pc/mod/a.archive", b"A")
    _put(game, "archive/pc/mod/b.archive", b"B")

    real_hardlink = install_service.hardlink
    calls = {"n": 0}

    def flaky_hardlink(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:  # fail on the 2nd file (after its move into staging)
            raise OSError("boom")
        return real_hardlink(src, dst)

    monkeypatch.setattr(install_service, "hardlink", flaky_hardlink)

    with pytest.raises(OSError):
        adopt_mod(game, "RB", ["archive/pc/mod/a.archive", "archive/pc/mod/b.archive"], session)

    # No data loss: BOTH files restored to the game dir as real files.
    assert (Path(game.install_path) / "archive/pc/mod/a.archive").read_bytes() == b"A"
    assert (Path(game.install_path) / "archive/pc/mod/b.archive").read_bytes() == b"B"
    assert session.exec(select(InstalledMod).where(InstalledMod.name == "RB")).first() is None
    # No journal row left "done" — all flipped to "failed" on rollback.
    entries = session.exec(select(DeployJournalEntry)).all()
    assert entries
    assert all(e.status == "failed" for e in entries)


def test_adopt_refuses_cross_volume(session, game, monkeypatch):
    from rippermod_manager.services import install_service
    from rippermod_manager.services.vfs.primitives import VfsError

    monkeypatch.setattr(install_service, "same_volume", lambda *a, **k: False)
    _put(game, "archive/pc/mod/cv.archive")
    with pytest.raises(VfsError, match="different volumes"):
        adopt_mod(game, "CV", ["archive/pc/mod/cv.archive"], session)


def test_adopt_raises_when_nothing_adopted(session, game):
    # All paths missing -> no phantom 0-file InstalledMod; raise instead.
    with pytest.raises(ValueError, match="No adoptable files"):
        adopt_mod(game, "Empty", ["archive/pc/mod/ghost.archive"], session)
    assert session.exec(select(InstalledMod).where(InstalledMod.name == "Empty")).first() is None
