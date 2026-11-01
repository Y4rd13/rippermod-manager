import os
import zipfile
from pathlib import Path

import pytest
from sqlmodel import select

from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import ArchiveNexusLink, InstalledMod, InstalledModFile
from rippermod_manager.services.install_service import (
    adopt_mod,
    backfill_adopted_archives,
    toggle_mod,
    uninstall_mod,
)
from rippermod_manager.services.settings_helpers import get_setting


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


def _zip(game: Game, name: str, members: list[str], link_id: int | None = 4198) -> None:
    staging = Path(game.install_path) / "downloaded_mods"
    staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(staging / name, "w") as zf:
        for m in members:
            zf.writestr(m, b"x")


def _link(session, game: Game, name: str, mod_id: int = 4198) -> None:
    session.add(ArchiveNexusLink(game_id=game.id, filename=name, nexus_mod_id=mod_id))
    session.commit()


def test_adopt_links_archive_that_covers_the_files(session, game):
    _put(game, "archive/pc/mod/x.archive")
    _zip(game, "X-4198-1-0.zip", ["archive/pc/mod/x.archive"])
    _link(session, game, "X-4198-1-0.zip")
    result = adopt_mod(game, "X", ["archive/pc/mod/x.archive"], session, nexus_mod_id=4198)
    assert session.get(InstalledMod, result.installed_mod_id).source_archive == "X-4198-1-0.zip"


def test_adopt_does_not_link_archive_below_coverage(session, game):
    _put(game, "archive/pc/mod/x.archive")
    _put(game, "archive/pc/mod/y.archive")
    _zip(game, "X-4198-1-0.zip", ["archive/pc/mod/x.archive"])
    _link(session, game, "X-4198-1-0.zip")
    result = adopt_mod(
        game,
        "X",
        ["archive/pc/mod/x.archive", "archive/pc/mod/y.archive"],
        session,
        nexus_mod_id=4198,
    )
    assert session.get(InstalledMod, result.installed_mod_id).source_archive == ""


def test_adopt_links_archive_when_the_mod_created_an_extra_file(session, game):
    # Mod Settings case: the mod writes user.ini at runtime (5 of 6 adopted files are in the
    # archive, 83 %), and the archive ships readme/license that never reach the game folder.
    shipped = [
        f"red4ext/plugins/ms/{n}" for n in ("a.dll", "b.reds", "c.reds", "d.archive", "e.xl")
    ]
    adopted = [*shipped, "red4ext/plugins/ms/user.ini"]
    for rel in adopted:
        _put(game, rel)
    _zip(
        game,
        "MS-4198-1-0.zip",
        [*shipped, "red4ext/plugins/ms/readme.md", "red4ext/plugins/ms/license.md"],
    )
    _link(session, game, "MS-4198-1-0.zip")
    result = adopt_mod(game, "MS", adopted, session, nexus_mod_id=4198)
    assert session.get(InstalledMod, result.installed_mod_id).source_archive == "MS-4198-1-0.zip"


def test_adopt_does_not_link_a_small_archive_inside_a_larger_group(session, game):
    # The whole archive is on disk, but it covers only 1 of the 4 adopted files.
    adopted = [f"archive/pc/mod/{n}.archive" for n in ("a", "b", "c", "d")]
    for rel in adopted:
        _put(game, rel)
    _zip(game, "A-4198-1-0.zip", ["archive/pc/mod/a.archive"])
    _link(session, game, "A-4198-1-0.zip")
    result = adopt_mod(game, "A", adopted, session, nexus_mod_id=4198)
    assert session.get(InstalledMod, result.installed_mod_id).source_archive == ""


def test_adopt_does_not_link_fomod_archive(session, game):
    _put(game, "archive/pc/mod/x.archive")
    _zip(game, "X-4198-1-0.zip", ["fomod/ModuleConfig.xml", "archive/pc/mod/x.archive"])
    _link(session, game, "X-4198-1-0.zip")
    result = adopt_mod(game, "X", ["archive/pc/mod/x.archive"], session, nexus_mod_id=4198)
    assert session.get(InstalledMod, result.installed_mod_id).source_archive == ""


def test_adopt_links_best_covering_archive_of_the_same_mod(session, game):
    _put(game, "archive/pc/mod/x.archive")
    _put(game, "archive/pc/mod/y.archive")
    _zip(game, "Old-4198-1-0.zip", ["archive/pc/mod/x.archive"])
    _zip(game, "New-4198-2-0.zip", ["archive/pc/mod/x.archive", "archive/pc/mod/y.archive"])
    _link(session, game, "Old-4198-1-0.zip")
    _link(session, game, "New-4198-2-0.zip")
    result = adopt_mod(
        game,
        "X",
        ["archive/pc/mod/x.archive", "archive/pc/mod/y.archive"],
        session,
        nexus_mod_id=4198,
    )
    assert session.get(InstalledMod, result.installed_mod_id).source_archive == "New-4198-2-0.zip"


def test_adopt_without_nexus_id_links_nothing(session, game):
    _put(game, "archive/pc/mod/x.archive")
    _zip(game, "X-4198-1-0.zip", ["archive/pc/mod/x.archive"])
    _link(session, game, "X-4198-1-0.zip")
    result = adopt_mod(game, "X", ["archive/pc/mod/x.archive"], session)
    assert session.get(InstalledMod, result.installed_mod_id).source_archive == ""


def _previously_adopted(session, game, name="X", mod_id=4198) -> InstalledMod:
    mod = InstalledMod(
        game_id=game.id, name=name, staging_dir=name, source_archive="", nexus_mod_id=mod_id
    )
    session.add(mod)
    session.flush()
    session.add(
        InstalledModFile(
            installed_mod_id=mod.id,
            relative_path="archive/pc/mod/x.archive",
            source_path="archive/pc/mod/x.archive",
        )
    )
    session.commit()
    return mod


def test_backfill_links_previously_adopted_mod(session, game):
    mod = _previously_adopted(session, game)
    _zip(game, "X-4198-1-0.zip", ["archive/pc/mod/x.archive"])
    _link(session, game, "X-4198-1-0.zip")

    assert backfill_adopted_archives(game, session) == 1
    assert get_setting(session, f"adopt_archive_backfill_done:{game.id}") == "1"
    session.refresh(mod)
    assert mod.source_archive == "X-4198-1-0.zip"
    assert backfill_adopted_archives(game, session) == 0


def test_backfill_leaves_mod_without_covering_archive_and_still_marks_done(session, game):
    mod = _previously_adopted(session, game)
    assert backfill_adopted_archives(game, session) == 0
    session.refresh(mod)
    assert mod.source_archive == ""
    assert get_setting(session, f"adopt_archive_backfill_done:{game.id}") == "1"


def test_backfill_ignores_mods_that_already_have_an_archive(session, game):
    mod = _previously_adopted(session, game)
    mod.source_archive = "Keep.zip"
    session.add(mod)
    session.commit()
    _zip(game, "X-4198-1-0.zip", ["archive/pc/mod/x.archive"])
    _link(session, game, "X-4198-1-0.zip")
    assert backfill_adopted_archives(game, session) == 0
    session.refresh(mod)
    assert mod.source_archive == "Keep.zip"


def test_adopt_ignores_covering_archive_of_another_nexus_mod(session, game):
    _put(game, "archive/pc/mod/x.archive")
    _zip(game, "Other-9999-1-0.zip", ["archive/pc/mod/x.archive"])
    _link(session, game, "Other-9999-1-0.zip", mod_id=9999)
    result = adopt_mod(game, "X", ["archive/pc/mod/x.archive"], session, nexus_mod_id=4198)
    assert session.get(InstalledMod, result.installed_mod_id).source_archive == ""


def test_backfill_flag_is_per_game_so_every_game_gets_backfilled(session, game, tmp_path):
    other_dir = tmp_path / "game2"
    other_dir.mkdir()
    other = Game(name="CP2", domain_name="cyberpunk2077", install_path=str(other_dir))
    session.add(other)
    session.commit()
    session.refresh(other)
    for g in (game, other):
        _previously_adopted(session, g)
        _zip(g, "X-4198-1-0.zip", ["archive/pc/mod/x.archive"])
        _link(session, g, "X-4198-1-0.zip")

    assert backfill_adopted_archives(game, session) == 1
    assert backfill_adopted_archives(other, session) == 1
    assert backfill_adopted_archives(other, session) == 0
    assert get_setting(session, f"adopt_archive_backfill_done:{other.id}") == "1"
