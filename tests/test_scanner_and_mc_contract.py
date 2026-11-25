"""The secrecy scanner must not be vacuous (mutation checks), captions at engine level, the MC contract."""
import json

import pytest

from khqs.engine import views
from khqs.engine.effects import McInterrupt, McListen, McSay
from support.bots import Bots
from support.content_fixture import BANK
from support.flows import final_sim
from support.harness import new_sim
from support.randbots import random_bots
from support.secrecy import assert_no_leaks


def finished(seed=3, players=2, **kw):
    sim = new_sim(BANK, names=("Mina", "Junho", "Ray")[:players], seed=seed, **kw)
    random_bots(sim, seed)
    sim.until_ended()
    return sim


# ---------------------------------------------------------------- the scanner catches planted leaks
def test_scanner_catches_hidden_buzzer_text_in_snapshots(monkeypatch):
    orig = views.public_question

    def leaky(eng):
        d = orig(eng)
        if d and d["kind"] == "buzzer":
            d["text"] = eng.q.text
        return d
    monkeypatch.setattr(views, "public_question", leaky)
    with pytest.raises(AssertionError, match="schema problems"):  # the schema itself already refuses this one
        finished()
    with pytest.raises(AssertionError, match="hidden text"):  # and with schema checks off the scanner still finds it
        assert_no_leaks(finished(check=False))


def test_scanner_catches_early_picks_in_snapshots(monkeypatch):
    orig = views.round_public

    def leaky(eng):
        d = orig(eng)
        if d and d["kind"] == "ox" and d["revealedChoices"] is None and eng.round.picks:
            d["revealedChoices"] = [{"seat": s, "choice": c} for s, c in sorted(eng.round.picks.items())]
        return d
    monkeypatch.setattr(views, "round_public", leaky)
    with pytest.raises(AssertionError, match="OX picks shown"):
        assert_no_leaks(finished())


def test_scanner_catches_a_bet_in_another_players_phone_view(monkeypatch):
    orig = views.phone_view

    def leaky(eng, seat):
        v = orig(eng, seat)
        if v is not None and eng.phase == "final.betting":
            v["own"]["others"] = {s: eng.round.bets.get(s) for s in eng.players if s != seat}
        return v
    monkeypatch.setattr(views, "phone_view", leaky)
    sim = final_sim(bets={0: 97, 1: 113, 2: 71})
    sim.until_ended()
    with pytest.raises(AssertionError, match="phone view"):
        assert_no_leaks(sim, canary_bets={0: 97, 1: 113, 2: 71})


def test_scanner_catches_an_explanation_in_an_early_mc_command():
    sim = finished()
    q = sim.eng.content.questions[0]
    sim.mc_fx.insert(0, (1, McSay("t-x", "suspense", {"kind": q.explanation}), 0))
    with pytest.raises(AssertionError, match="MC suspense"):
        assert_no_leaks(sim)


def test_scanner_catches_an_early_credit_in_the_stream():
    sim = finished()
    sim.stream.insert(0, {"proto": "x", "type": "mc.caption", "sseq": 1, "at": 0, "data": {"text": "by Test Composer"}})
    with pytest.raises(AssertionError, match="leaks"):
        assert_no_leaks(sim)


# ---------------------------------------------------------------- captions
def cap(sim, uid, text, final=True):
    n = len(sim.stream)
    ok = sim.eng.mc_caption(uid, text, final)
    sim.pump()
    return ok, sim.stream[n:]


def test_captions_blocked_while_a_buzzer_question_is_read_then_allowed():
    sim = new_sim(BANK, names=("Mina",), seed=3, say_ms=5000)
    Bots(sim, ox=lambda s, q: "O")
    sim.until_phase("buzzer.reading")
    ok, out = cap(sim, 1, "At midnight what should you never look into", final=False)
    assert ok is False and out == []
    sim.until_type("question.text_revealed")
    ok, out = cap(sim, 2, "Buzzers are open, hurry!")
    assert ok and out[0]["data"] == {"utteranceId": "u-2", "text": "Buzzers are open, hurry!", "final": True}


def test_captions_never_carry_answers_explanations_or_credits_before_the_reveal():
    sim = new_sim(BANK, names=("Mina",), seed=3, say_ms=5000)
    Bots(sim, ox=lambda s, q: "O")
    sim.until_phase("ox.answering")
    assert cap(sim, 1, "Get your paddles ready!")[0] is True
    assert cap(sim, 2, "The answer is O!")[0] is False
    assert cap(sim, 3, "Octopuses really do have three hearts.")[0] is False  # the explanation
    sim.until_type("answer.revealed")
    sim.run(100)
    assert cap(sim, 4, "Octopuses really do have three hearts.")[0] is True  # public now


def test_music_credits_and_title_blocked_until_reveal():
    sim = new_sim(BANK, names=("Mina",), seed=__import__("support.seeds", fromlist=["x"]).seed_for_track("dm"))
    Bots(sim, ox=lambda s, q: "O")
    sim.until_type("av.play")
    assert cap(sim, 1, "That was Danse Macabre", final=False)[0] is False
    assert cap(sim, 2, "A piece by Test Composer", final=True)[0] is False
    assert cap(sim, 3, "Did you enjoy the listen?")[0] is True


def test_partial_leading_words_of_an_answer_are_held_back():
    sim = new_sim(BANK, names=("Mina",), seed=__import__("support.seeds", fromlist=["x"]).seed_for_track("dm"))
    Bots(sim, ox=lambda s, q: "O")
    sim.until_type("av.play")
    ok, out = cap(sim, 7, "I believe this is Danse ", final=False)
    assert ok and out[0]["data"]["text"] == "I believe this is"
    assert cap(sim, 7, "I believe this is Danse Macabre", final=False)[0] is False


def test_player_speech_is_never_in_the_stream():
    sim = new_sim(BANK, names=("Mina",), seed=3)
    Bots(sim, ox=lambda s, q: "O", buzz=lambda q, l: 1 if q == 4 else None,
         voice=lambda q, s, n: ("xyzzy plugh", "clear", True))
    sim.until_type("buzzer.judged")
    blob = json.dumps([sim.stream, sim.snapshots, sim.views], ensure_ascii=False)
    assert "xyzzy" not in blob and not sim.of("buzzer.answer_heard")


# ---------------------------------------------------------------- MC contract
def test_buzz_interrupts_the_mc_once_and_status_returns_to_idle():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=3, say_ms=5000)
    Bots(sim, ox=lambda s, q: "O" if s == 0 else "X")
    sim.until_phase("buzzer.reading")
    n = sum(isinstance(e, McInterrupt) for _, e, _ in sim.mc_fx)
    sim.act(0, {"type": "buzz"})
    assert sum(isinstance(e, McInterrupt) for _, e, _ in sim.mc_fx) == n + 1
    assert sim.eng.mc_status == "listening"  # the holder is being listened to
    assert [x for x in sim.stream if x["type"] == "mc.status"][-1]["data"]["status"] == "listening"


def test_mc_status_follows_speech_and_is_deduplicated():
    sim = new_sim(BANK, names=("Mina",), say_ms=2000)
    sim.until_type("act.started")
    st = [m["data"]["status"] for m in sim.stream if m["type"] == "mc.status"]
    assert st[:2] == ["speaking", "idle"] and all(a != b for a, b in zip(st, st[1:]))


def test_played_tokens_only_count_once():
    sim = new_sim(BANK, names=("Mina",), say_ms=10_000_000)
    sim.run_until(lambda: any(isinstance(e, McSay) for _, e, _ in sim.mc_fx), what="greeting")
    tok = next(e.token for _, e, _ in sim.mc_fx if isinstance(e, McSay))
    assert sim.eng.mc_played("t-999") is False
    assert sim.eng.mc_failed(tok) is True and sim.eng.mc_played(tok) is False


def test_without_an_mc_the_engine_issues_no_mc_commands_and_still_finishes():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=3, mc=False)
    Bots(sim, ox=lambda s, q: "O" if s == 0 else "X", buzz=lambda q, l: 1 if q in (4, 6, 7) else None,
         text=lambda q, s: "x", bet=lambda s, sc: sc, choice=lambda s: "B")
    sim.until_ended()
    assert not [e for _, e, _ in sim.mc_fx if isinstance(e, (McSay, McListen, McInterrupt))]
    assert not [m for m in sim.stream if m["type"] == "mc.status"]


def test_reactions_carry_public_results_only_after_the_ack():
    sim = new_sim(BANK, names=("Mina",), seed=3, ack_ms=1500)
    Bots(sim, ox=lambda s, q: "O")
    sim.until_type("answer.revealed")
    rev = sim.of("answer.revealed")[0]
    t_msg = sim.stream_t[sim.stream.index(rev)]
    sim.run(3_000)
    cues = [(t, e) for _, e, t in sim.mc_fx if isinstance(e, McSay) and e.cue == "react_answer"]
    assert len(cues) == 1 and cues[0][0] == t_msg + 1500
    assert cues[0][1].facts["answer"] == "O" and cues[0][1].facts["results"] == [{"name": "Mina", "correct": True}]
