"""Seeded random players. Decisions are memoised per situation so a re-run gives the same game."""
from __future__ import annotations

import random

from support.bots import Bots


def random_bots(sim, seed, *, p_buzz=0.8, p_ox_skip=0.05):
    rng = random.Random(seed)
    memo: dict = {}
    qs = {q.number: q for q in sim.eng.content.questions}

    def pick(key, fn):
        if key not in memo:
            memo[key] = fn()
        return memo[key]

    def ox(seat, qn):
        return pick(("ox", seat, qn), lambda: None if rng.random() < p_ox_skip else rng.choice("OX"))

    def buzz(qn, level):
        e = sim.eng
        key = ("buzz", qn, level, e.phase, len(e.round.attempts))
        return pick(key, lambda: rng.choice(sorted(e.players)) if rng.random() < p_buzz else None)

    def voice(qn, seat, n):
        def make():
            r = rng.random()
            q = qs[qn]
            if r < 0.15:
                return ("mumble", "unclear", True)
            if r < 0.22:
                return ("hello?", "clear", False)
            if r < 0.55:
                return (rng.choice([q.answer, *q.aliases]), "clear", True)
            return (rng.choice(["a pillow", "dance floor", "Moonlight Sonata"]), "clear", True)
        return pick(("voice", qn, seat, n, len(sim.eng.round.attempts)), make)

    def text(qn, seat):
        q = qs[qn]
        return pick(("text", qn, seat, len(sim.eng.round.attempts)), lambda: rng.choice([q.answer, "nope"]))

    def bet(seat, score):
        return pick(("bet", seat), lambda: rng.choice([0, score, rng.randint(0, score), None]))

    def choice(seat):
        return pick(("choice", seat), lambda: rng.choice(["A", "B", "C", "D", None]))

    reason = lambda seat: pick(("reason", seat), lambda: rng.choice(["knew", "hunch", "crowd", None]))  # noqa: E731
    decision = lambda seat: pick(("dec", seat), lambda: rng.choice([True, False, None]))  # noqa: E731
    return Bots(sim, ox=ox, buzz=buzz, voice=voice, text=text, bet=bet, choice=choice, reason=reason, decision=decision)
