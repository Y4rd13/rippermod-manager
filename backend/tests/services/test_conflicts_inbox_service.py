"""Tests for the conflicts inbox 'reinstall' resolution guard."""

import zipfile
from pathlib import Path

import pytest
from sqlmodel import Session

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.conflicts_inbox_service import (
    ResolveRefusedError,
    get_conflicts_overview,
    get_mod_conflict_detail,
    resolve_conflict,
)

FOMOD_ARCHIVE = "fomod-mod.zip"


@pytest.fixture
def game_with_fomod_mod(engine, tmp_path: Path):
    """A game with an installed mod whose source archive is a FOMOD installer."""
    install_path = tmp_path / "game"
    staging = install_path / "downloaded_mods"
    staging.mkdir(parents=True)
    with zipfile.ZipFile(staging / FOMOD_ARCHIVE, "w") as zf:
        zf.writestr("fomod/ModuleConfig.xml", "<config/>")
        zf.writestr("fomod/info.xml", "<fomod/>")
        zf.writestr("Option A/archive/pc/mod/a.archive", b"a")
        zf.writestr("Option B/archive/pc/mod/b.archive", b"b")

    with Session(engine) as s:
        game = Game(
            name="Cyberpunk 2077",
            domain_name="cyberpunk2077",
            install_path=str(install_path),
        )
        s.add(game)
        s.flush()
        s.add(GameModPath(game_id=game.id, relative_path="archive/pc/mod"))
        mod = InstalledMod(game_id=game.id, name="Fomod Mod", source_archive=FOMOD_ARCHIVE)
        s.add(mod)
        s.flush()
        s.add(InstalledModFile(installed_mod_id=mod.id, relative_path="archive/pc/mod/a.archive"))
        s.commit()
        s.refresh(game)
        s.refresh(mod)
        _ = game.mod_paths
        s.expunge_all()
    return game, mod


def test_resolve_refuses_fomod_archive_without_uninstalling(session, game_with_fomod_mod):
    game, mod = game_with_fomod_mod
    with pytest.raises(ResolveRefusedError, match="FOMOD installer"):
        resolve_conflict(game, mod, session)
    assert session.get(InstalledMod, mod.id) is not None


def test_resolve_router_returns_409_for_fomod(client, game_with_fomod_mod):
    game, mod = game_with_fomod_mod
    r = client.post(
        f"/api/v1/games/{game.name}/conflicts/inbox/{mod.id}/resolve",
        json={"action": "reinstall"},
    )
    assert r.status_code == 409
    assert "Reinstall it from Archives" in r.json()["detail"]


def test_resolve_reinstalls_a_plain_archive(session, tmp_path: Path):
    install_path = tmp_path / "game2"
    staging = install_path / "downloaded_mods"
    staging.mkdir(parents=True)
    with zipfile.ZipFile(staging / "plain.zip", "w") as zf:
        zf.writestr("archive/pc/mod/plain.archive", b"data")

    game = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(install_path))
    session.add(game)
    session.flush()
    session.add(GameModPath(game_id=game.id, relative_path="archive/pc/mod"))
    mod = InstalledMod(game_id=game.id, name="plain", source_archive="plain.zip")
    session.add(mod)
    session.commit()
    session.refresh(game)

    result = resolve_conflict(game, mod, session)

    assert result.files_extracted == 1
    assert session.get(InstalledMod, result.installed_mod_id) is not None


def _game_with_mods_sharing(session, tmp_path: Path, shared: str):
    """Two installed mods whose source archives both hold ``shared``; the second owns it."""
    install_path = tmp_path / "game3"
    staging = install_path / "downloaded_mods"
    staging.mkdir(parents=True)
    game = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(install_path))
    session.add(game)
    session.flush()
    session.add(GameModPath(game_id=game.id, relative_path="archive/pc/mod"))
    mods = []
    for label in ("a", "b"):
        with zipfile.ZipFile(staging / f"{label}.zip", "w") as zf:
            zf.writestr(shared, b"x")
            zf.writestr(f"archive/pc/mod/{label}.archive", b"x")
        mod = InstalledMod(game_id=game.id, name=f"Mod {label}", source_archive=f"{label}.zip")
        session.add(mod)
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path=shared))
        session.add(
            InstalledModFile(
                installed_mod_id=mod.id, relative_path=f"archive/pc/mod/{label}.archive"
            )
        )
        mods.append(mod)
    session.commit()
    session.refresh(game)
    return game, mods


def test_inbox_ignores_root_doc_file(session, tmp_path: Path):
    game, _ = _game_with_mods_sharing(session, tmp_path, "codes.txt")

    overview = get_conflicts_overview(game, session)

    assert overview.total_conflicts == 0
    assert overview.summaries == []


def test_inbox_detail_ignores_root_doc_file(session, tmp_path: Path):
    game, mods = _game_with_mods_sharing(session, tmp_path, "codes.txt")

    detail = get_mod_conflict_detail(game, mods[0], session)

    assert detail.evidence == []


def test_inbox_counts_doc_file_inside_folder(session, tmp_path: Path):
    game, mods = _game_with_mods_sharing(session, tmp_path, "bin/x64/mods/x/icon.png")

    overview = get_conflicts_overview(game, session)

    assert overview.total_conflicts == 1
    assert len(get_mod_conflict_detail(game, mods[0], session).evidence) == 1
