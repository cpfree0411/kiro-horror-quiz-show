import random

import pytest

from khqs.rules import betrayal, scoring


def test_rank_competition_style():
    assert scoring.rank_scores({0: 10, 1: 10, 2: 0}) == {0: 1, 1: 1, 2: 3}
    assert scoring.rank_scores({0: 5, 1: 20, 2: 5}) == {0: 2, 1: 1, 2: 2}
    assert scoring.rank_scores({0: 0}) == {0: 1}
    assert scoring.rank_scores({0: 0, 1: 0, 2: 0}) == {0: 1, 1: 1, 2: 1}


def test_leaders_and_winners():
    assert scoring.winners({0: 10, 1: 30, 2: 30}) == [1, 2]
    assert scoring.leaders({0: 0}) == frozenset({0})


@pytest.mark.parametrize("value,score,ok", [
    (0, 0, True), (0, 50, True), (50, 50, True), (51, 50, False), (-1, 50, False),
    (True, 50, False), (False, 50, False), (5.0, 50, False), (5.5, 50, False),
    ("5", 50, False), (None, 50, False), ([5], 50, False),
])
def test_bet_validation(value, score, ok):
    assert scoring.is_valid_bet(value, score) is ok


def test_all_in_includes_zero_at_zero():
    assert scoring.is_all_in(0, 0)
    assert scoring.is_all_in(80, 80)
    assert not scoring.is_all_in(0, 10)


def test_final_delta_never_goes_below_zero_when_bet_valid():
    assert scoring.final_delta(100, True) == 100
    assert scoring.final_delta(120, False) == -120
    assert 80 + scoring.final_delta(80, False) == 0


def test_bet_reveal_order_lowest_first_ties_by_seat_leader_last():
    assert scoring.bet_reveal_order({0: 120, 1: 200, 2: 80}) == [2, 0, 1]
    assert scoring.bet_reveal_order({0: 50, 1: 50, 2: 10}) == [2, 0, 1]


def test_streak():
    assert betrayal.next_streak(0, True, True) == 1
    assert betrayal.next_streak(1, True, True) == 2
    assert betrayal.next_streak(1, False, True) == 0
    assert betrayal.next_streak(1, True, False) == 0  # solo
    assert betrayal.should_offer(2) and not betrayal.should_offer(1)


def test_target_unique_lowest():
    assert betrayal.pick_target({0: 20, 1: 10, 2: 30}, random.Random(1)) == (1, "lowest", [])


def test_target_tie_uses_seeded_rng_over_sorted_seats():
    a = betrayal.pick_target({0: 10, 1: 10}, random.Random(7))
    b = betrayal.pick_target({1: 10, 0: 10}, random.Random(7))
    assert a == b and a[1] == "tied_random" and a[2] == [0, 1] and a[0] in (0, 1)
    seen = {betrayal.pick_target({0: 10, 1: 10, 2: 10}, random.Random(s))[0] for s in range(40)}
    assert seen == {0, 1, 2}


def test_flip():
    assert betrayal.flip("O") == "X" and betrayal.flip("X") == "O"
