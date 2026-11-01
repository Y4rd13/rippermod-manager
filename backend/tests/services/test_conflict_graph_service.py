"""Conflict graph: only mods on disk, one node per mod, cached by a DB + staging fingerprint."""

import json
import os
import zipfile
from pathlib import Path

import pytest
from sqlmodel import select

from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.conflict import ConflictEvidence, ConflictKind, Severity
from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.download import DownloadJob
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import ArchiveNexusLink, InstalledMod, InstalledModFile
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.services import conflict_graph_service
from rippermod_manager.services.conflict_graph_service import (
    build_conflict_graph,
    conflict_count,
)

SHARED = "archive/pc/mod/x.archive"


@pytest.fixture(autouse=True)
def _clear_graph_cache():
    conflict_graph_service._GRAPH_CACHE.clear()
    yield
    conflict_graph_service._GRAPH_CACHE.clear()


@pytest.fixture
def game(session, tmp_path) -> Game:
    g = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(tmp_path))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="archive/pc/mod"))
    session.commit()
    session.refresh(g)
    (tmp_path / "downloaded_mods").mkdir()
    return g


def _archive(game: Game, filename: str, paths: list[str], mtime: int | None = None) -> Path:
    path = Path(game.install_path) / "downloaded_mods" / filename
    with zipfile.ZipFile(path, "w") as zf:
        for p in paths:
            zf.writestr(p, b"x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _on_disk(session, game: Game, nexus_mod_id: int, score: float = 1.0) -> None:
    group = ModGroup(game_id=game.id, display_name=f"Mod {nexus_mod_id}", confidence=0.9)
    nd = NexusDownload(game_id=game.id, nexus_mod_id=nexus_mod_id, mod_name=f"Mod {nexus_mod_id}")
    session.add(group)
    session.add(nd)
    session.flush()
    session.add(
        ModNexusCorrelation(
            mod_group_id=group.id, nexus_download_id=nd.id, score=score, method="filename_id"
        )
    )
    session.commit()


def _installed(session, game: Game, name: str, nexus_mod_id: int | None, paths: list[str], **kw):
    mod = InstalledMod(game_id=game.id, name=name, nexus_mod_id=nexus_mod_id, **kw)
    session.add(mod)
    session.flush()
    for p in paths:
        session.add(InstalledModFile(installed_mod_id=mod.id, relative_path=p))
    session.commit()
    return mod


def test_archive_without_mod_on_disk_is_excluded(session, game):
    _on_disk(session, game, 101)
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED])
    _archive(game, "ModB-202-1-0-1700000000.zip", [SHARED])

    g = build_conflict_graph(game, session)

    assert {n.nexus_mod_id for n in g.nodes} == set()
    assert conflict_count(game, session).mods_with_conflicts == 0


def test_two_on_disk_mods_sharing_a_file_count_two(session, game):
    _on_disk(session, game, 101)
    _on_disk(session, game, 202)
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED, "archive/pc/mod/a.archive"])
    _archive(game, "ModB-202-1-0-1700000000.zip", [SHARED, "archive/pc/mod/b.archive"])

    s = conflict_count(game, session)

    assert s.mods_with_conflicts == 2 and s.file_conflicts == 1


def test_archive_nexus_id_from_link_or_download_job(session, game):
    _on_disk(session, game, 101)
    _on_disk(session, game, 202)
    _archive(game, "Linked.zip", [SHARED])
    _archive(game, "Downloaded.zip", [SHARED])
    session.add(ArchiveNexusLink(game_id=game.id, filename="Linked.zip", nexus_mod_id=101))
    session.add(
        DownloadJob(
            game_id=game.id,
            nexus_mod_id=202,
            nexus_file_id=1,
            file_name="Downloaded.zip",
            status="completed",
        )
    )
    session.commit()

    assert conflict_count(game, session).mods_with_conflicts == 2


def test_one_node_per_unmanaged_mod_uses_newest_archive(session, game):
    _on_disk(session, game, 101)
    _on_disk(session, game, 202)
    y = "archive/pc/mod/y.archive"
    # Two archives of Nexus 101 sharing a path; only the old one also ships y.archive.
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED, y], mtime=1_700_000_000)
    _archive(game, "ModA-101-2-0-1700000100.zip", [SHARED], mtime=1_700_000_100)
    # Nexus 202 conflicts only with the old archive of 101.
    _archive(game, "ModB-202-1-0-1700000000.zip", [y])

    g = build_conflict_graph(game, session)

    assert len([n for n in g.nodes if n.nexus_mod_id == 101]) <= 1
    assert conflict_count(game, session).mods_with_conflicts == 0


def test_managed_mod_absorbs_its_other_archives(session, game):
    z = "archive/pc/mod/z.archive"
    _installed(session, game, "ModA", 101, [SHARED])
    _on_disk(session, game, 202)
    # A loose archive of the managed mod 101; it alone would collide with 202 on z.archive.
    _archive(game, "ModA-101-2-0-1700000100.zip", [SHARED, z])
    _archive(game, "ModB-202-1-0-1700000000.zip", [z])

    assert conflict_count(game, session).mods_with_conflicts == 0


@pytest.mark.parametrize(("optional_nexus_id", "expected"), [(101, 0), (202, 2)])
def test_two_files_of_the_same_mod_do_not_conflict(session, game, optional_nexus_id, expected):
    # Two managed mods whose .archive files override the same resource (a resource edge).
    main = _installed(session, game, "Main file", 101, ["archive/pc/mod/main.archive"])
    opt = _installed(
        session, game, "Optional file", optional_nexus_id, ["archive/pc/mod/opt.archive"]
    )
    for mod, filename in ((main, "main.archive"), (opt, "opt.archive")):
        session.add(
            ArchiveEntryIndex(
                game_id=game.id,
                installed_mod_id=mod.id,
                archive_filename=filename,
                resource_hash=1,
            )
        )
    session.add(
        ConflictEvidence(
            game_id=game.id,
            kind=ConflictKind.archive_resource,
            severity=Severity.low,
            key="1",
            detail=json.dumps(
                {"winner_archive": "main.archive", "loser_archives": ["opt.archive"]}
            ),
        )
    )
    session.commit()

    assert conflict_count(game, session).mods_with_conflicts == expected


def test_dismissed_managed_mod_is_not_counted(session, game):
    _installed(session, game, "ModA", 101, [SHARED], conflict_dismissed=True)
    _on_disk(session, game, 202)
    _archive(game, "ModB-202-1-0-1700000000.zip", [SHARED])

    s = conflict_count(game, session)

    assert s.mods_with_conflicts == 1
    assert s.file_conflicts == 1


def test_cache_invalidates_when_a_mod_is_installed(session, game, monkeypatch):
    _on_disk(session, game, 101)
    _on_disk(session, game, 202)
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED])
    _archive(game, "ModB-202-1-0-1700000000.zip", [SHARED])

    opened: list[Path] = []
    real_open = conflict_graph_service.open_archive

    def counting_open(path):
        opened.append(path)
        return real_open(path)

    monkeypatch.setattr(conflict_graph_service, "open_archive", counting_open)

    build_conflict_graph(game, session)
    first = len(opened)
    assert first > 0

    build_conflict_graph(game, session)
    assert len(opened) == first

    _installed(session, game, "Manual", None, ["r6/scripts/other.reds"])
    build_conflict_graph(game, session)
    assert len(opened) > first


def test_cache_invalidates_when_a_correlation_is_confirmed(session, game):
    _on_disk(session, game, 101)
    _on_disk(session, game, 202, score=0.5)
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED])
    _archive(game, "ModB-202-1-0-1700000000.zip", [SHARED])
    assert conflict_count(game, session).mods_with_conflicts == 0

    row = session.exec(select(ModNexusCorrelation).where(ModNexusCorrelation.score == 0.5)).one()
    row.confirmed_by_user = True
    session.add(row)
    session.commit()

    assert conflict_count(game, session).mods_with_conflicts == 2


def test_resource_hash_bypasses_the_cache(session, game, monkeypatch):
    _on_disk(session, game, 101)
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED])
    build_conflict_graph(game, session)

    opened: list[Path] = []
    real_open = conflict_graph_service.open_archive

    def counting_open(path):
        opened.append(path)
        return real_open(path)

    monkeypatch.setattr(conflict_graph_service, "open_archive", counting_open)
    build_conflict_graph(game, session, resource_hash="abc")

    assert opened


def test_cache_invalidates_when_an_archive_link_is_changed(session, game):
    _on_disk(session, game, 101)
    _on_disk(session, game, 202)
    _archive(game, "Linked.zip", [SHARED])
    _archive(game, "ModB-202-1-0-1700000000.zip", [SHARED])
    link = ArchiveNexusLink(game_id=game.id, filename="Linked.zip", nexus_mod_id=303)
    session.add(link)
    session.commit()
    assert conflict_count(game, session).mods_with_conflicts == 0

    link.nexus_mod_id = 101
    session.add(link)
    session.commit()

    assert conflict_count(game, session).mods_with_conflicts == 2


def test_cache_invalidates_when_a_managed_mod_is_relinked(session, game):
    _on_disk(session, game, 101)
    mod = _installed(session, game, "Manual", None, [SHARED])
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED])
    assert conflict_count(game, session).mods_with_conflicts == 2

    mod.nexus_mod_id = 101
    session.add(mod)
    session.commit()

    assert conflict_count(game, session).mods_with_conflicts == 0


def test_cache_invalidates_when_an_installed_file_is_renamed(session, game):
    _on_disk(session, game, 101)
    mod = _installed(session, game, "Manual", None, ["archive/pc/mod/a.archive"])
    _archive(game, "ModA-101-1-0-1700000000.zip", ["archive/pc/mod/zz_shared.archive"])
    assert conflict_count(game, session).mods_with_conflicts == 0

    f = mod.files[0]
    f.relative_path = "archive/pc/mod/zz_shared.archive"
    session.add(f)
    session.commit()

    assert conflict_count(game, session).mods_with_conflicts == 2


def _resource_edge(session, game: Game, winner: str, loser: str) -> None:
    session.add(
        ConflictEvidence(
            game_id=game.id,
            kind=ConflictKind.archive_resource,
            severity=Severity.low,
            key="1",
            detail=json.dumps({"winner_archive": winner, "loser_archives": [loser]}),
        )
    )
    session.commit()


def _index(session, game: Game, mod: InstalledMod, filename: str) -> None:
    session.add(
        ArchiveEntryIndex(
            game_id=game.id, installed_mod_id=mod.id, archive_filename=filename, resource_hash=1
        )
    )
    session.commit()


def test_cache_invalidates_when_the_newest_confirmed_correlation_is_reassigned(session, game):
    _on_disk(session, game, 202)
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED])
    _archive(game, "ModB-202-1-0-1700000000.zip", [SHARED])
    group = ModGroup(game_id=game.id, display_name="Reassigned", confidence=0.9)
    nd_101 = NexusDownload(game_id=game.id, nexus_mod_id=101, mod_name="A")
    nd_303 = NexusDownload(game_id=game.id, nexus_mod_id=303, mod_name="C")
    session.add_all([group, nd_101, nd_303])
    session.flush()
    newest = ModNexusCorrelation(
        mod_group_id=group.id,
        nexus_download_id=nd_101.id,
        score=1.0,
        method="manual",
        confirmed_by_user=True,
    )
    session.add(newest)
    session.commit()
    old_id = newest.id
    assert conflict_count(game, session).mods_with_conflicts == 2

    # As routers/mods.py reassign_correlation: delete the group's rows, insert a confirmed one.
    session.delete(newest)
    session.flush()
    reassigned = ModNexusCorrelation(
        mod_group_id=group.id,
        nexus_download_id=nd_303.id,
        score=1.0,
        method="manual",
        confirmed_by_user=True,
    )
    session.add(reassigned)
    session.commit()
    assert reassigned.id == old_id  # SQLite reuses the freed highest id

    assert conflict_count(game, session).mods_with_conflicts == 0


def test_cache_invalidates_when_evidence_is_rewritten_under_the_same_id(session, game):
    main = _installed(session, game, "Main", 101, ["archive/pc/mod/main.archive"])
    other = _installed(session, game, "Other", 202, ["archive/pc/mod/other.archive"])
    _index(session, game, main, "main.archive")
    _index(session, game, other, "other.archive")
    _resource_edge(session, game, "main.archive", "other.archive")
    old = session.exec(select(ConflictEvidence)).one()
    old_id = old.id
    assert conflict_count(game, session).mods_with_conflicts == 2

    # As the conflict engine's reindex: delete the kind's rows, write the new ones.
    session.delete(old)
    session.flush()
    _resource_edge(session, game, "main.archive", "unindexed.archive")
    assert session.exec(select(ConflictEvidence)).one().id == old_id

    assert conflict_count(game, session).mods_with_conflicts == 0


def test_cache_invalidates_when_archives_are_indexed_after_install(session, game):
    main = _installed(session, game, "Main", 101, ["archive/pc/mod/main.archive"])
    other = _installed(session, game, "Other", 202, ["archive/pc/mod/other.archive"])
    _resource_edge(session, game, "main.archive", "other.archive")
    assert conflict_count(game, session).mods_with_conflicts == 0

    _index(session, game, main, "main.archive")
    _index(session, game, other, "other.archive")

    assert conflict_count(game, session).mods_with_conflicts == 2


def test_cache_invalidates_when_an_installed_file_row_is_replaced_under_the_same_id(session, game):
    _on_disk(session, game, 101)
    mod = _installed(session, game, "Manual", None, ["archive/pc/mod/a.archive"])
    _archive(game, "ModA-101-1-0-1700000000.zip", ["archive/pc/mod/b.archive"])
    assert conflict_count(game, session).mods_with_conflicts == 0

    old = mod.files[0]
    old_id = old.id
    session.delete(old)
    session.flush()
    new = InstalledModFile(installed_mod_id=mod.id, relative_path="archive/pc/mod/b.archive")
    session.add(new)
    session.commit()
    assert new.id == old_id  # same id, same count, same path length

    assert conflict_count(game, session).mods_with_conflicts == 2


def test_cache_invalidates_when_a_managed_mod_is_renamed(session, game):
    _on_disk(session, game, 101)
    mod = _installed(session, game, "Old name", None, [SHARED])
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED])
    build_conflict_graph(game, session)

    mod.name = "New name"
    session.add(mod)
    session.commit()

    labels = {n.label for n in build_conflict_graph(game, session).nodes}
    assert "New name" in labels


def test_cache_invalidates_when_a_download_job_completes(session, game):
    _on_disk(session, game, 101)
    _on_disk(session, game, 202)
    _archive(game, "ModA-101-1-0-1700000000.zip", [SHARED])
    _archive(game, "Downloaded.zip", [SHARED])
    job = DownloadJob(
        game_id=game.id,
        nexus_mod_id=202,
        nexus_file_id=1,
        file_name="Downloaded.zip",
        status="downloading",
    )
    session.add(job)
    session.commit()
    assert conflict_count(game, session).mods_with_conflicts == 0

    job.status = "completed"
    session.add(job)
    session.commit()

    assert conflict_count(game, session).mods_with_conflicts == 2
