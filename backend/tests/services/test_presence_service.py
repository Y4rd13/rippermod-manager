from rippermod_manager.models.correlation import ModNexusCorrelation
from rippermod_manager.models.install import InstalledMod
from rippermod_manager.models.mod import ModGroup
from rippermod_manager.models.nexus import NexusDownload
from rippermod_manager.services.presence_service import (
    ON_DISK_MIN_SCORE,
    nexus_presence,
    winning_correlations,
)


def _correlate(
    session,
    game,
    nexus_mod_id: int,
    score: float,
    confirmed: bool = False,
    name: str = "Mod",
) -> ModGroup:
    group = ModGroup(game_id=game.id, display_name=name, confidence=0.9)
    nd = NexusDownload(game_id=game.id, nexus_mod_id=nexus_mod_id, mod_name=name)
    session.add(group)
    session.add(nd)
    session.flush()
    session.add(
        ModNexusCorrelation(
            mod_group_id=group.id,
            nexus_download_id=nd.id,
            score=score,
            method="filename_id",
            confirmed_by_user=confirmed,
        )
    )
    session.commit()
    return group


def test_threshold_constant():
    assert ON_DISK_MIN_SCORE == 0.75


def test_score_at_threshold_counts_on_disk(session, make_game):
    game = make_game()
    _correlate(session, game, 4885, 0.75)
    p = nexus_presence(game, session)
    assert p.is_on_disk(4885) is True
    assert p.possible(4885) is None


def test_score_just_below_threshold_is_possible(session, make_game):
    game = make_game()
    _correlate(session, game, 4886, 0.7499)
    p = nexus_presence(game, session)
    assert p.is_on_disk(4886) is False
    assert p.possible(4886) is not None


def test_low_score_is_possible_match(session, make_game):
    game = make_game()
    group = _correlate(session, game, 28966, 0.47)
    p = nexus_presence(game, session)
    assert p.is_on_disk(28966) is False
    possible = p.possible(28966)
    assert possible is not None
    assert possible.score == 0.47
    assert possible.mod_group_id == group.id
    assert possible.confirmed is False


def test_confirmed_low_score_counts_on_disk(session, make_game):
    game = make_game()
    _correlate(session, game, 77, 0.4, confirmed=True)
    p = nexus_presence(game, session)
    assert p.is_on_disk(77) is True
    assert p.possible(77) is None


def test_managed_ids_count_on_disk(session, make_game):
    game = make_game()
    session.add(InstalledMod(game_id=game.id, name="Managed", nexus_mod_id=4198))
    session.commit()
    p = nexus_presence(game, session)
    assert p.is_on_disk(4198) is True
    assert 4198 in p.managed_ids
    assert 4198 not in p.matches


def test_managed_id_hides_possible_match(session, make_game):
    game = make_game()
    _correlate(session, game, 4199, 0.3)
    session.add(InstalledMod(game_id=game.id, name="Managed", nexus_mod_id=4199))
    session.commit()
    p = nexus_presence(game, session)
    assert p.is_on_disk(4199) is True
    assert p.possible(4199) is None


def test_installed_mod_without_nexus_id_is_not_managed(session, make_game):
    game = make_game()
    session.add(InstalledMod(game_id=game.id, name="Local only"))
    session.commit()
    p = nexus_presence(game, session)
    assert p.managed_ids == set()


def test_unknown_id_is_not_on_disk(session, make_game):
    game = make_game()
    p = nexus_presence(game, session)
    assert p.is_on_disk(1) is False
    assert p.possible(1) is None


def test_dedup_keeps_highest_scoring_group(session, make_game):
    game = make_game()
    _correlate(session, game, 12001, 0.5, name="Weak")
    strong = _correlate(session, game, 12001, 1.0, name="Strong")
    p = nexus_presence(game, session)
    assert p.matches[12001].score == 1.0
    assert p.matches[12001].on_disk is True
    assert p.matches[12001].mod_group_id == strong.id


def test_other_game_is_ignored(session, make_game):
    game = make_game()
    other = make_game(name="Other", domain_name="other")
    _correlate(session, other, 555, 1.0)
    p = nexus_presence(game, session)
    assert p.is_on_disk(555) is False


def test_winning_correlations_keeps_best_correlation_per_group(session, make_game):
    game = make_game()
    group = _correlate(session, game, 100, 0.4)
    nd2 = NexusDownload(game_id=game.id, nexus_mod_id=101, mod_name="Better")
    session.add(nd2)
    session.flush()
    session.add(
        ModNexusCorrelation(mod_group_id=group.id, nexus_download_id=nd2.id, score=0.9, method="x")
    )
    session.commit()
    winners = winning_correlations(session, game.id)
    corr, nd = winners[group.id]
    assert corr.score == 0.9
    assert nd.nexus_mod_id == 101


def test_winning_correlations_drops_losing_group(session, make_game):
    game = make_game()
    loser = _correlate(session, game, 12001, 0.5)
    winner = _correlate(session, game, 12001, 1.0)
    winners = winning_correlations(session, game.id)
    assert set(winners) == {winner.id}
    assert loser.id not in winners
