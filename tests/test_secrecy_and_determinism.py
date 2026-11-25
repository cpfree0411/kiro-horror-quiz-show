"""Acceptance: a secrecy scan over every emitted stream; determinism; logs."""
import json
import logging

import pytest

from khqs.engine.effects import McSay
from support.content_fixture import BANK
from support.harness import new_sim
from support.randbots import random_bots
from support.secrecy import assert_no_leaks

NAMES = {1: ("Mina",), 2: ("Mina", "Junho"), 3: ("Mina", "Junho", "Ray")}


def play(players, seed, game_index=0, **kw):
    sim = new_sim(BANK, names=NAMES[players], seed=seed, game_index=game_index, **kw)
    random_bots(sim, seed)
    sim.until_ended()
    return sim


@pytest.mark.parametrize("players,seed,game_index", [(1, 11, 0), (2, 12, 1), (3, 13, 0), (3, 14, 1), (2, 15, 0)])
def test_secrecy_scan_over_every_channel_in_random_full_games(players, seed, game_index):
    sim = play(players, seed, game_index)
    assert sim.stream[-1]["type"] == "game.ended"
    assert [m["sseq"] for m in sim.stream] == list(range(1, len(sim.stream) + 1))
    assert len(sim.of("score.settled")) == 8 and len(sim.of("answer.revealed")) == 8
    assert_no_leaks(sim)


def test_secrecy_with_distinct_bet_canaries_and_a_close_final():
    from support.flows import final_sim
    sim = final_sim(bets={0: 97, 1: 113, 2: 71}, choices={0: "B", 1: "A", 2: "B"})
    sim.until_ended()
    assert_no_leaks(sim, canary_bets={0: 97, 1: 113, 2: 71})


def test_mc_commands_before_a_reveal_carry_no_secrets_and_use_only_whitelisted_facts():
    from khqs.engine.effects import CUE_FACTS
    sim = play(3, 21)
    for _, e, _t in sim.mc_fx:
        if isinstance(e, McSay):
            assert e.cue in CUE_FACTS and set(e.facts) <= CUE_FACTS[e.cue], e


def test_same_seed_same_inputs_gives_the_identical_stream():
    a, b = play(3, 5), play(3, 5)
    assert json.dumps(a.stream, sort_keys=True) == json.dumps(b.stream, sort_keys=True)
    assert [type(e).__name__ + repr(getattr(e, "facts", "")) for _, e, _ in a.mc_fx] == \
           [type(e).__name__ + repr(getattr(e, "facts", "")) for _, e, _ in b.mc_fx]
    c = play(3, 6)
    assert json.dumps(a.stream, sort_keys=True) != json.dumps(c.stream, sort_keys=True)


def test_logs_carry_phase_and_player_count_only(caplog):
    caplog.set_level(logging.DEBUG)
    sim = new_sim(BANK, names=("Zoltán", "민아"), seed=3)
    random_bots(sim, 3)
    sim.until_ended()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "phase=" in text and "players=2" in text
    secrets = ["Zoltán", "민아", "Mirror", "Pumpkin", "Danse", "Frankenstein"] + [p.credential for p in sim.eng.players.values()]
    assert not [s for s in secrets if s in text]
    assert all(r.name.startswith("khqs") for r in caplog.records)


@pytest.mark.parametrize("players,seed", [(2, 31), (3, 32)])
def test_no_shaming_words_anywhere_the_engine_writes(players, seed):
    """Product rule: never 'last', 'last place', 'loser', 'worst' (docs/GAME_RULES.md section 5)."""
    import re
    sim = play(players, seed)
    texts = []
    for m in sim.stream:
        if m["type"] in ("question.presented", "question.text_revealed", "answer.revealed", "seat.joined", "show.opening",
                         "finale.results", "finale.winner", "snapshot"):
            continue  # content and names are not engine-written
        texts.append(json.dumps(m["data"], ensure_ascii=False))
    texts += [json.dumps(m["data"]["title"]) for m in sim.of("act.started")]
    for _, e, _t in sim.mc_fx:
        if isinstance(e, McSay) and e.cue not in ("read_ox", "read_buzzer", "read_final", "react_answer", "greeting", "act_intro",
                                                  "react_winner", "farewell", "final_intro"):
            texts.append(json.dumps(e.facts, ensure_ascii=False))
    bad = re.compile(r"\b(last|worst|loser|losers)\b", re.I)
    assert not [t for t in texts if bad.search(t)]
    assert bad.search("in last place") and not bad.search("Ghosts")  # the pattern itself works
