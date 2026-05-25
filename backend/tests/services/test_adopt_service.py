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
