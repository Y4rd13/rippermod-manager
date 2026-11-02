"""Integration tests for ConflictEngine orchestration."""

import pytest
from sqlmodel import select

from rippermod_manager.models.conflict import ConflictEvidence
from rippermod_manager.models.game import Game, GameModPath
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.conflicts.engine import ConflictEngine


@pytest.fixture
def game(session, tmp_path):
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    g = Game(name="EngineTest", domain_name="cyberpunk2077", install_path=str(game_dir))
    session.add(g)
    session.flush()
    session.add(GameModPath(game_id=g.id, relative_path="archive/pc/mod"))
    session.commit()
    session.refresh(g)
    return g


class TestConflictEngine:
    def test_run_with_no_mods(self, session, game):
        engine = ConflictEngine()
        evidence = engine.run(game, session)
        assert evidence == []

    def test_run_finds_archive_entry_conflicts(self, session, game):
        mod_a = InstalledMod(game_id=game.id, name="A")
        mod_b = InstalledMod(game_id=game.id, name="B")
        session.add_all([mod_a, mod_b])
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod_a.id, relative_path="shared.dll"))
        session.add(InstalledModFile(installed_mod_id=mod_b.id, relative_path="shared.dll"))
        session.commit()

        engine = ConflictEngine()
        evidence = engine.run(game, session)
        assert len(evidence) >= 1

    def test_run_persists_evidence(self, session, game):
        mod_a = InstalledMod(game_id=game.id, name="A")
        mod_b = InstalledMod(game_id=game.id, name="B")
        session.add_all([mod_a, mod_b])
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod_a.id, relative_path="shared.dll"))
        session.add(InstalledModFile(installed_mod_id=mod_b.id, relative_path="shared.dll"))
        session.commit()

        engine = ConflictEngine()
        evidence = engine.run(game, session)

        persisted = session.exec(
            select(ConflictEvidence).where(ConflictEvidence.game_id == game.id)
        ).all()
        assert len(persisted) == len(evidence)

    def test_reindex_replaces_old_evidence(self, session, game):
        mod_a = InstalledMod(game_id=game.id, name="A")
        mod_b = InstalledMod(game_id=game.id, name="B")
        session.add_all([mod_a, mod_b])
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod_a.id, relative_path="f.txt"))
        session.add(InstalledModFile(installed_mod_id=mod_b.id, relative_path="f.txt"))
        session.commit()

        engine = ConflictEngine()
        engine.run(game, session)
        second = engine.run(game, session)

        persisted = session.exec(
            select(ConflictEvidence).where(ConflictEvidence.game_id == game.id)
        ).all()
        assert len(persisted) == len(second)

    def test_run_does_not_duplicate_across_reindexes(self, session, game):
        mod_a = InstalledMod(game_id=game.id, name="A")
        mod_b = InstalledMod(game_id=game.id, name="B")
        session.add_all([mod_a, mod_b])
        session.flush()
        session.add(InstalledModFile(installed_mod_id=mod_a.id, relative_path="overlap.txt"))
        session.add(InstalledModFile(installed_mod_id=mod_b.id, relative_path="overlap.txt"))
        session.commit()

        engine = ConflictEngine()
        for _ in range(3):
            engine.run(game, session)

        persisted = session.exec(
            select(ConflictEvidence).where(ConflictEvidence.game_id == game.id)
        ).all()
        # Should have exactly one conflict, not accumulated across runs
        archive_conflicts = [e for e in persisted if e.key == "overlap.txt"]
        assert len(archive_conflicts) == 1


def test_reindex_job_persists_evidence(session, game):
    from rippermod_manager.services.conflicts import auto_reindex

    mod_a = InstalledMod(game_id=game.id, name="A")
    mod_b = InstalledMod(game_id=game.id, name="B")
    session.add_all([mod_a, mod_b])
    session.flush()
    session.add(InstalledModFile(installed_mod_id=mod_a.id, relative_path="shared.dll"))
    session.add(InstalledModFile(installed_mod_id=mod_b.id, relative_path="shared.dll"))
    session.commit()

    auto_reindex._reindex_job(game.id)
    session.expire_all()

    rows = session.exec(select(ConflictEvidence).where(ConflictEvidence.game_id == game.id)).all()
    assert rows != []


def test_auto_reindex_waits_two_seconds():
    from rippermod_manager.services.conflicts import auto_reindex

    assert auto_reindex._runner.debounce_s == 2.0


def test_request_conflict_reindex_hands_the_game_id_to_the_runner(background_requests):
    from rippermod_manager.services.conflicts import auto_reindex

    auto_reindex.request_conflict_reindex(5)
    assert background_requests["conflicts"] == [5]


def test_detectors_run_with_no_write_transaction_open(session, game, monkeypatch):
    """Detectors can be slow: the old evidence is deleted only after the last one.

    Holding SQLite's write lock while they run would make every other write wait
    for the busy timeout (the reindex now runs after each toggle and install).
    """
    from rippermod_manager.models.conflict import ConflictKind, Severity
    from rippermod_manager.services.conflicts import engine as engine_mod

    mod_a = InstalledMod(game_id=game.id, name="A")
    session.add(mod_a)
    session.commit()
    session.add(
        ConflictEvidence(
            game_id=game.id,
            kind=ConflictKind.archive_entry,
            severity=Severity.low,
            key="old",
        )
    )
    session.commit()

    open_tx: list[bool] = []

    class _Spy:
        def __init__(self, kind):
            self.kind = kind

        def detect(self, _game, _mods, s, **_kw):
            open_tx.append(s.connection().connection.dbapi_connection.in_transaction)
            return []

    monkeypatch.setattr(
        engine_mod,
        "get_all_detectors",
        lambda: [_Spy(ConflictKind.archive_entry), _Spy(ConflictKind.tweak_key)],
    )
    ConflictEngine().run(game, session)
    assert open_tx == [False, False]
    left = session.exec(select(ConflictEvidence).where(ConflictEvidence.game_id == game.id)).all()
    assert left == []
