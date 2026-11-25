"""Betrayal chance rules (docs/GAME_RULES.md section 5). Pure functions."""
from __future__ import annotations

import random
from collections.abc import Mapping

TRIGGER_STREAK = 2


def next_streak(streak: int, unanimous: bool, competitive: bool) -> int:
    """Consecutive fully unanimous rounds. Solo never builds a streak."""
    if not competitive:
        return 0
    return streak + 1 if unanimous else 0


def should_offer(streak: int) -> bool:
    return streak >= TRIGGER_STREAK


def pick_target(scores: Mapping[int, int], rng: random.Random) -> tuple[int, str, list[int]]:
    """Return (seat, selection, tiedSeats). The target is the current lowest score.

    A tie is broken with the seeded RNG over the sorted tied seats. `tiedSeats` is empty for a unique lowest.
    """
    low = min(scores.values())
    tied = sorted(seat for seat, s in scores.items() if s == low)
    if len(tied) == 1:
        return tied[0], "lowest", []
    return rng.choice(tied), "tied_random", tied


def flip(choice: str) -> str:
    return "X" if choice == "O" else "O"
