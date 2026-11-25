from support.bots import Bots
from support.content_fixture import BANK
from support.harness import new_sim


def final_sim(bets=None, choices=None, scores=None, names=("Mina", "Junho", "Ray"), seed=4, **kw):
    """Play acts 1 and 2 quickly, then set scores (white-box) just before the final's betting."""
    sim = new_sim(BANK, names=names, seed=seed, **kw)
    n = len(names)
    bets = bets if bets is not None else {0: 100, 1: 120, 2: 80}
    choices = choices if choices is not None else {0: "B", 1: "A", 2: "B"}
    Bots(sim, ox=lambda s, q: "O", bet=lambda s, sc_: bets.get(s), choice=lambda s: choices.get(s))
    sim.until_phase("final.intro")
    for seat, score in (scores if scores is not None else {0: 120, 1: 200, 2: 80}).items():
        if seat in sim.eng.players:
            sim.eng.players[seat].score = score
    return sim
