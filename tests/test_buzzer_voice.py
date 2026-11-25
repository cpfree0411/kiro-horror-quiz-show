"""Act 2 buzzer: who may buzz, voice answers, recognition failures, phone fallback, timeouts."""
import pytest

from khqs.engine.effects import McInterrupt, McListen, McSay, McStopListen
from support.bots import Bots
from support.content_fixture import BANK
from support.harness import new_sim
from support.seeds import seed_for_track


def at_q(names=("Mina", "Junho"), q=4, **kw):
    """A game paused when the buzzer question number `q` is reading (regular) or media (music)."""
    sim = new_sim(BANK, names=names, seed=seed_for_track("dm"), **kw)
    Bots(sim, ox=lambda s, n: "O" if s == 0 else "X")
    phase = "buzzer.reading" if q != 5 else "buzzer.media"
    sim.run_until(lambda: sim.eng.q is not None and sim.eng.q.number == q and sim.eng.phase == phase, what=f"q{q}")
    return sim


def buzz(sim, seat):
    return sim.act(seat, {"type": "buzz"})


def voice(sim, heard, recognition="clear", voiced=True):
    l = sim.last_listen("answer")
    ok = sim.eng.mc_voice_answer(l.listen_id, heard, recognition, voiced)
    sim.pump()
    return ok


def says(sim, cue):
    return [e for _, e, _ in sim.mc_fx if isinstance(e, McSay) and e.cue == cue]


def test_first_buzz_wins_and_duplicates_locked_and_unarmed_are_rejected():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=7)
    Bots(sim, ox=lambda s, n: "O" if s == 0 else "X")
    sim.until_phase("buzzer.presenting")
    assert buzz(sim, 0).error == "not_now"  # not armed during the presentation gate
    sim.until_phase("buzzer.reading")
    assert buzz(sim, 1).ok
    assert buzz(sim, 0).error == "busy"
    assert buzz(sim, 1).error == "busy"
    assert len(sim.of("buzzer.pressed")) == 1 and sim.of("buzzer.pressed")[0]["data"]["seat"] == 1
    voice(sim, "nonsense answer")  # wrong with evidence
    sim.until_phase("buzzer.reading")  # resumed
    assert buzz(sim, 1).error == "locked_out"
    assert buzz(sim, 0).ok


def test_disconnected_player_cannot_buzz_or_answer():
    sim = at_q()
    sim.eng.phone_connection(0, False)
    assert buzz(sim, 0).error == "disconnected"
    assert sim.act(0, {"type": "text_answer", "text": "x"}).error == "disconnected"
    sim.eng.phone_connection(0, True)
    assert buzz(sim, 0).ok
    assert [m["data"] for m in sim.of("seat.connection")][-2:] == [{"seat": 0, "connected": False}, {"seat": 0, "connected": True}]


def test_wrong_voice_answer_with_evidence_is_judged_wrong_exactly_once():
    sim = at_q()
    buzz(sim, 0)
    assert voice(sim, "a pillow")
    sim.until_type("buzzer.judged")
    j = sim.of("buzzer.judged")
    assert len(j) == 1 and j[0]["data"] == {"seat": 0, "correct": False, "lockedOut": [0]}
    l = sim.listens[-1]
    assert sim.eng.mc_voice_answer(l.listen_id, "mirror", "clear", True) is False  # duplicate delivery ignored


def test_exact_for_regular_korean_alias_ok_and_answer_heard_never_sent():
    sim = at_q()
    buzz(sim, 0)
    voice(sim, "거울")
    sim.until_type("buzzer.judged")
    assert sim.of("buzzer.judged")[0]["data"]["correct"] is True
    sim.until_type("score.settled", 4)
    assert not sim.of("buzzer.answer_heard")


def test_recognition_failure_is_not_a_wrong_answer_two_failures_open_phone_text_box():
    sim = at_q()
    buzz(sim, 0)
    l1 = sim.last_listen("answer")
    assert l1.attempt == 1
    voice(sim, "mirror", recognition="unclear")
    assert not sim.of("buzzer.judged")
    l2 = sim.last_listen("answer")
    assert l2.listen_id != l1.listen_id and l2.attempt == 2 and l2.deadline == l1.deadline  # same window
    assert says(sim, "ask_again")[0].facts == {"name": "Mina", "attempt": 2}
    assert sim.eng.phone_view(0)["own"]["textBox"] is False
    voice(sim, "mirror", voiced=False)  # confident text but no voiced audio: still a failure
    assert not sim.of("buzzer.judged")
    assert sim.eng.phone_view(0)["screen"] == "answer_text" and sim.eng.phone_view(0)["own"]["textBox"] is True
    assert says(sim, "phone_fallback")[0].facts == {"name": "Mina"}
    assert sim.eng.mc_voice_answer(l2.listen_id, "mirror", "clear", True) is False  # voice is closed now
    assert sim.act(1, {"type": "text_answer", "text": "mirror"}).error == "not_holder"
    assert sim.act(0, {"type": "text_answer", "text": "Mirror"}).ok
    sim.until_type("buzzer.judged")
    assert sim.of("buzzer.judged")[0]["data"]["correct"] is True


def test_empty_heard_is_a_failure():
    sim = at_q()
    buzz(sim, 0)
    voice(sim, "   ")
    assert not sim.of("buzzer.judged") and sim.last_listen("answer").attempt == 2


def test_choose_typing_right_away_and_text_box_rules():
    sim = at_q()
    buzz(sim, 0)
    assert sim.act(0, {"type": "text_answer", "text": "mirror"}).error == "not_now"  # box not open yet
    assert sim.act(1, {"type": "choose_typing"}).error == "not_holder"
    assert sim.act(0, {"type": "choose_typing"}).ok
    assert any(isinstance(e, McStopListen) for _, e, _ in sim.mc_fx)
    assert sim.act(0, {"type": "text_answer", "text": "x" * 61}).error == "bad_input"
    assert sim.act(0, {"type": "text_answer", "text": 5}).error == "bad_input"
    assert sim.act(0, {"type": "text_answer", "text": "  \n "}).error == "bad_input"
    assert sim.act(0, {"type": "text_answer", "text": "pillow"}).ok
    assert sim.act(0, {"type": "text_answer", "text": "mirror"}).error in ("not_holder", "already_answered")
    sim.until_type("buzzer.judged")
    assert sim.of("buzzer.judged")[0]["data"]["correct"] is False


def test_answer_window_deadline_is_public_and_real_and_timeout_counts_wrong():
    sim = at_q()
    t = sim.clock.now_ms()
    buzz(sim, 0)
    ph = [m for m in sim.of("phase.changed") if m["data"]["phase"] == "buzzer.answering"][-1]
    assert ph["data"]["deadline"] == t + sim.eng.cfg.buzzer_answer_ms
    assert sim.eng.snapshot()["data"]["game"]["deadline"] == ph["data"]["deadline"]
    sim.run_until(lambda: sim.of("buzzer.judged"), what="timeout judgement")
    assert sim.clock.now_ms() >= ph["data"]["deadline"]
    assert sim.of("buzzer.judged")[0]["data"] == {"seat": 0, "correct": False, "lockedOut": [0]}


def test_music_answer_is_lenient_regular_is_not():
    sim = at_q(q=5)
    buzz(sim, 1)
    sim.run(500)  # the fake stage confirms the interrupt
    voice(sim, "hmm I think it's dance macabre")
    sim.until_type("buzzer.judged")
    assert sim.of("buzzer.judged")[0]["data"]["correct"] is True


def test_no_mc_means_phone_text_only():
    sim = new_sim(BANK, names=("Mina",), seed=7, mc=False)
    Bots(sim, ox=lambda s, n: "O")
    sim.until_phase("buzzer.open")  # with no MC the reading takes no time, so buzzing starts at the open window
    assert buzz(sim, 1).ok  # a solo player sits in the middle seat
    assert sim.eng.phone_view(1)["own"]["textBox"] is True
    assert not sim.listens and not [e for _, e, _ in sim.mc_fx if isinstance(e, (McSay, McListen))]
    assert sim.act(1, {"type": "text_answer", "text": "mirror"}).ok
    sim.until_ended()


def test_reading_failsafe_moves_on_when_the_mc_never_finishes():
    sim = new_sim(BANK, names=("Mina",), seed=7, say_ms=10_000_000)
    Bots(sim, ox=lambda s, n: "O")
    sim.until_phase("buzzer.reading")
    t = sim.clock.now_ms()
    sim.until_type("question.text_revealed")
    assert 45_000 <= sim.clock.now_ms() - t < 46_000
    assert any(isinstance(e, McInterrupt) and e.reason == "failsafe" for _, e, _ in sim.mc_fx)


def test_early_correct_answer_ends_the_reading_and_the_text_is_never_revealed():
    sim = at_q(names=("Mina",))
    buzz(sim, 1)
    voice(sim, "mirror")
    sim.until_type("score.settled", 4)
    assert not sim.of("question.text_revealed")
    text = BANK.sets[0].buzzers[0].text
    assert all(text not in repr(m) for m in sim.stream)
    assert all(text not in repr(s) for s in sim.snapshots if s["sseq"] <= sim.stream[-1]["sseq"] and s["data"]["question"] and s["data"]["question"]["id"] == "q-bz-01")
    assert [d["delta"] for d in sim.of("score.settled")[-1]["data"]["deltas"]] == [20]


def test_everyone_locked_out_still_reveals_text_after_reading_then_suspense():
    sim = at_q(names=("Mina",))
    buzz(sim, 1)
    voice(sim, "pillow")
    sim.until_type("question.text_revealed")
    types = [m["type"] for m in sim.stream if m["type"] != "mc.status"]
    # no buzzer.open window when nobody can still buzz: the phase after the text goes to suspense
    sim.until_type("answer.revealed", 4)
    phases = [m["data"]["phase"] for m in sim.stream if m["type"] == "phase.changed"]
    i = len(phases) - 1 - phases[::-1].index("buzzer.reading")
    assert phases[i + 1] == "buzzer.suspense"
    assert sim.of("answer.revealed")[-1]["data"]["results"] == [{"seat": 1, "correct": False}]


def test_open_window_is_15s_and_nobody_buzzing_goes_to_reveal():
    sim = at_q()
    sim.until_type("question.text_revealed")
    t = sim.clock.now_ms()
    op = next(m for m in reversed(sim.stream) if m["type"] == "phase.changed" and m["data"]["phase"] == "buzzer.open")
    assert op["data"]["deadline"] == sim.stream_t[sim.stream.index(op)] + 15_000
    sim.until_type("score.settled", 4)
    assert sim.of("answer.revealed")[-1]["data"]["results"] == []
    assert [d["delta"] for d in sim.of("score.settled")[-1]["data"]["deltas"]] == [0, 0]


def test_wrong_buzz_in_open_window_gives_a_fresh_window_to_the_rest():
    sim = at_q()
    sim.until_phase("buzzer.open")
    buzz(sim, 0)
    voice(sim, "pillow")
    sim.until_phase("buzzer.open")
    assert sim.of("buzzer.judged")[-1]["data"]["lockedOut"] == [0]
    assert buzz(sim, 0).error == "locked_out"
    assert buzz(sim, 1).ok
    voice(sim, "mirror")
    sim.until_type("score.settled", 4)
    assert [d["delta"] for d in sim.of("score.settled")[-1]["data"]["deltas"]] == [0, 20]
