"""Tests for dependency_graph.build_dependency_pairs()."""

from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.nexus import NexusModRequirement
from rippermod_manager.services.conflicts.dependency_graph import build_dependency_pairs


class TestBuildDependencyPairs:
    def test_empty_when_no_mods(self, session):
        assert build_dependency_pairs([], session) == set()

    def test_empty_when_no_nexus_ids(self, session, make_game):
        game = make_game()
        mod_a = InstalledMod(game_id=game.id, name="A")
        mod_b = InstalledMod(game_id=game.id, name="B")
        session.add_all([mod_a, mod_b])
        session.commit()
        session.refresh(mod_a)
        session.refresh(mod_b)

        assert build_dependency_pairs([mod_a, mod_b], session) == set()

    def test_forward_dependency_creates_pair(self, session, make_game):
        game = make_game()
        mod_a = InstalledMod(game_id=game.id, name="A", nexus_mod_id=100)
        mod_b = InstalledMod(game_id=game.id, name="B", nexus_mod_id=200)
        session.add_all([mod_a, mod_b])
        session.flush()

        # mod 100 requires mod 200
        session.add(NexusModRequirement(nexus_mod_id=100, required_mod_id=200, mod_name="B"))
        session.commit()
        session.refresh(mod_a)
        session.refresh(mod_b)

        pairs = build_dependency_pairs([mod_a, mod_b], session)
        assert len(pairs) == 1
        pair = next(iter(pairs))
        assert pair == (min(mod_a.id, mod_b.id), max(mod_a.id, mod_b.id))

    def test_reverse_dependency_creates_pair(self, session, make_game):
        game = make_game()
        mod_a = InstalledMod(game_id=game.id, name="A", nexus_mod_id=100)
        mod_b = InstalledMod(game_id=game.id, name="B", nexus_mod_id=200)
        session.add_all([mod_a, mod_b])
        session.flush()

        # mod 200 requires mod 100 (reverse from A's perspective)
        session.add(
            NexusModRequirement(
                nexus_mod_id=200, required_mod_id=100, mod_name="A", is_reverse=True
            )
        )
        session.commit()
        session.refresh(mod_a)
        session.refresh(mod_b)

        pairs = build_dependency_pairs([mod_a, mod_b], session)
        assert len(pairs) == 1

    def test_one_side_not_installed(self, session, make_game):
        game = make_game()
        mod_a = InstalledMod(game_id=game.id, name="A", nexus_mod_id=100)
        session.add(mod_a)
        session.flush()

        # mod 100 requires mod 999 (not installed)
        session.add(NexusModRequirement(nexus_mod_id=100, required_mod_id=999, mod_name="Missing"))
        session.commit()
        session.refresh(mod_a)

        pairs = build_dependency_pairs([mod_a], session)
        assert pairs == set()

    def test_deduplicates_pairs(self, session, make_game):
        game = make_game()
        mod_a = InstalledMod(game_id=game.id, name="A", nexus_mod_id=100)
        mod_b = InstalledMod(game_id=game.id, name="B", nexus_mod_id=200)
        session.add_all([mod_a, mod_b])
        session.flush()

        # Both forward and reverse requirement between same mods
        session.add(NexusModRequirement(nexus_mod_id=100, required_mod_id=200))
        session.add(NexusModRequirement(nexus_mod_id=100, required_mod_id=200, is_reverse=True))
        session.commit()
        session.refresh(mod_a)
        session.refresh(mod_b)

        pairs = build_dependency_pairs([mod_a, mod_b], session)
        assert len(pairs) == 1
