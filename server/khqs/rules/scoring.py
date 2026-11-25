"""Scoring, ranking and final-bet rules. Pure functions (docs/GAME_RULES.md sections 3, 7)."""
from __future__ import annotations

from collections.abc import Mapping

OX_POINTS = 10
BUZZER_POINTS = 20


def rank_scores(scores: Mapping[int, int]) -> dict[int, int]:
    """Competition ranking: ties share a rank and the next rank skips (1, 1, 3)."""
    return {seat: 1 + sum(1 for other in scores.values() if other > s) for seat, s in scores.items()}


def leaders(scores: Mapping[int, int]) -> frozenset[int]:
    """Seats holding rank 1."""
    if not scores:
        return frozenset()
    top = max(scores.values())
    return frozenset(seat for seat, s in scores.items() if s == top)


def winners(scores: Mapping[int, int]) -> list[int]:
    return sorted(leaders(scores))


def is_valid_bet(value: object, score: int) -> bool:
    """An integer in [0, score]. Booleans, floats, strings, negatives and oversized values are rejected."""
    return type(value) is int and 0 <= value <= score


def is_all_in(bet: int, score: int) -> bool:
    """Betting everything counts, including 0 at a score of 0."""
    return bet == score


def final_delta(bet: int, correct: bool) -> int:
    return bet if correct else -bet


def bet_reveal_order(scores: Mapping[int, int]) -> list[int]:
    """Ascending by pre-settlement score, ties by seat, so the leader is revealed last."""
    return sorted(scores, key=lambda seat: (scores[seat], seat))
