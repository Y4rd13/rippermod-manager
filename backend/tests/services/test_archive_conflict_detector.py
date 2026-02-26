"""Tests for the archive conflict detector."""

from __future__ import annotations

from rippermod_manager.models.archive_index import ArchiveEntryIndex
from rippermod_manager.models.conflict import ConflictSeverity, ConflictType
from rippermod_manager.services.archive_conflict_detector import (
    detect_archive_conflicts,
    summarize_conflicts,
)


def _add_entry(
    session,
    game_id: int,
    archive_filename: str,
    resource_hash: int,
    installed_mod_id: int | None = None,
) -> None:
    session.add(
        ArchiveEntryIndex(
            game_id=game_id,
            installed_mod_id=installed_mod_id,
            archive_filename=archive_filename,
            archive_relative_path=f"archive/pc/mod/{archive_filename}",
            resource_hash=resource_hash,
            sha1_hex="0" * 40,
        )
    )
    session.flush()


class TestDetectArchiveConflicts:
    def test_no_conflicts_when_disjoint(self, session, make_game):
        game = make_game()
        _add_entry(session, game.id, "a.archive", 100)
        _add_entry(session, game.id, "b.archive", 200)

        result = detect_archive_conflicts(session, game.id)
        assert result == []

    def test_single_hash_collision(self, session, make_game):
        game = make_game()
        _add_entry(session, game.id, "a.archive", 100, installed_mod_id=1)
        _add_entry(session, game.id, "b.archive", 100, installed_mod_id=2)

        result = detect_archive_conflicts(session, game.id)
        assert len(result) == 1
        assert result[0].conflict_type == ConflictType.ARCHIVE_HASH
        assert result[0].resource_hash == 100
        assert result[0].winner_archive == "a.archive"
        assert result[0].loser_archive == "b.archive"
        assert result[0].winner_installed_mod_id == 1
        assert result[0].loser_installed_mod_id == 2

    def test_winner_is_alphabetically_first(self, session, make_game):
        game = make_game()
        _add_entry(session, game.id, "zzz.archive", 42)
        _add_entry(session, game.id, "aaa.archive", 42)

        result = detect_archive_conflicts(session, game.id)
        assert len(result) == 1
        assert result[0].winner_archive == "aaa.archive"
        assert result[0].loser_archive == "zzz.archive"

    def test_multiple_losers_for_same_hash(self, session, make_game):
        game = make_game()
        _add_entry(session, game.id, "a.archive", 50)
        _add_entry(session, game.id, "b.archive", 50)
        _add_entry(session, game.id, "c.archive", 50)

        result = detect_archive_conflicts(session, game.id)
        assert len(result) == 2
        assert result[0].winner_archive == "a.archive"
        assert result[0].loser_archive == "b.archive"
        assert result[1].winner_archive == "a.archive"
        assert result[1].loser_archive == "c.archive"

    def test_deterministic_ordering(self, session, make_game):
        game = make_game()
        _add_entry(session, game.id, "x.archive", 200)
        _add_entry(session, game.id, "y.archive", 200)
        _add_entry(session, game.id, "x.archive", 100)
        _add_entry(session, game.id, "y.archive", 100)

        r1 = detect_archive_conflicts(session, game.id)
        r2 = detect_archive_conflicts(session, game.id)
        assert r1 == r2
        assert r1[0].resource_hash == 100
        assert r1[1].resource_hash == 200

    def test_no_conflicts_different_games(self, session, make_game):
        game1 = make_game(name="Game1", domain_name="game1")
        game2 = make_game(name="Game2", domain_name="game2")
        _add_entry(session, game1.id, "a.archive", 100)
        _add_entry(session, game2.id, "b.archive", 100)

        assert detect_archive_conflicts(session, game1.id) == []
        assert detect_archive_conflicts(session, game2.id) == []

    def test_empty_index_returns_empty(self, session, make_game):
        game = make_game()
        assert detect_archive_conflicts(session, game.id) == []

    def test_multiple_hashes_some_conflicting(self, session, make_game):
        game = make_game()
        _add_entry(session, game.id, "a.archive", 10)
        _add_entry(session, game.id, "a.archive", 20)
        _add_entry(session, game.id, "b.archive", 20)
        _add_entry(session, game.id, "b.archive", 30)

        result = detect_archive_conflicts(session, game.id)
        assert len(result) == 1
        assert result[0].resource_hash == 20


class TestSummarizeConflicts:
    def test_critical_severity(self, session, make_game):
        """Archive where all entries lose."""
        game = make_game()
        # b.archive has 1 entry, and that entry also exists in a.archive
        _add_entry(session, game.id, "a.archive", 100)
        _add_entry(session, game.id, "b.archive", 100)

        summaries = summarize_conflicts(session, game.id)
        loser = next(s for s in summaries if s.archive_filename == "b.archive")
        assert loser.severity == ConflictSeverity.CRITICAL
        assert loser.losing_entries == 1
        assert loser.total_entries == 1

    def test_info_severity_for_winner(self, session, make_game):
        """Archive that wins all its conflicts."""
        game = make_game()
        _add_entry(session, game.id, "a.archive", 100)
        _add_entry(session, game.id, "b.archive", 100)

        summaries = summarize_conflicts(session, game.id)
        winner = next(s for s in summaries if s.archive_filename == "a.archive")
        assert winner.severity == ConflictSeverity.INFO
        assert winner.winning_entries == 1
        assert winner.losing_entries == 0

    def test_moderate_severity(self, session, make_game):
        """Archive losing < 50% of entries."""
        game = make_game()
        # c.archive has 3 entries total, loses 1 (33%)
        _add_entry(session, game.id, "a.archive", 100)
        _add_entry(session, game.id, "c.archive", 100)
        _add_entry(session, game.id, "c.archive", 200)
        _add_entry(session, game.id, "c.archive", 300)

        summaries = summarize_conflicts(session, game.id)
        c = next(s for s in summaries if s.archive_filename == "c.archive")
        assert c.severity == ConflictSeverity.MODERATE
        assert c.losing_entries == 1
        assert c.total_entries == 3

    def test_high_severity(self, session, make_game):
        """Archive losing > 50% of entries."""
        game = make_game()
        # d.archive has 3 entries total, loses 2 (67%)
        _add_entry(session, game.id, "a.archive", 100)
        _add_entry(session, game.id, "a.archive", 200)
        _add_entry(session, game.id, "d.archive", 100)
        _add_entry(session, game.id, "d.archive", 200)
        _add_entry(session, game.id, "d.archive", 300)

        summaries = summarize_conflicts(session, game.id)
        d = next(s for s in summaries if s.archive_filename == "d.archive")
        assert d.severity == ConflictSeverity.HIGH
        assert d.losing_entries == 2
        assert d.total_entries == 3

    def test_sorted_by_severity_then_name(self, session, make_game):
        game = make_game()
        # a.archive: winner (INFO)
        # z_mod.archive: all entries lose (CRITICAL)
        _add_entry(session, game.id, "a.archive", 100)
        _add_entry(session, game.id, "z_mod.archive", 100)

        summaries = summarize_conflicts(session, game.id)
        assert summaries[0].severity == ConflictSeverity.CRITICAL
        assert summaries[0].archive_filename == "z_mod.archive"
        assert summaries[1].severity == ConflictSeverity.INFO
        assert summaries[1].archive_filename == "a.archive"

    def test_conflicting_archives_listed(self, session, make_game):
        game = make_game()
        _add_entry(session, game.id, "a.archive", 100)
        _add_entry(session, game.id, "b.archive", 100)
        _add_entry(session, game.id, "c.archive", 100)

        summaries = summarize_conflicts(session, game.id)
        a = next(s for s in summaries if s.archive_filename == "a.archive")
        assert a.conflicting_archives == ("b.archive", "c.archive")

    def test_empty_returns_empty(self, session, make_game):
        game = make_game()
        assert summarize_conflicts(session, game.id) == []
