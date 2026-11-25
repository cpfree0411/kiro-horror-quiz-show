"""Phone actions and views, final bets and settlement."""
import json

import pytest

from khqs.engine.rounds import BETRAYAL_REASONS
from support.bots import Bots
from support.content_fixture import BANK
from support.flows import final_sim
from support.harness import new_sim


# ---------------------------------------------------------------- OX picks and views
def ox_sim(names=("Mina", "Junho")):
    sim = new_sim(BANK, names=names, seed=3)
    sim.until_phase("ox.answering")
    return sim


def test_ox_pick_validation_lock_in_and_own_view_only():
    sim = ox_sim()
    assert sim.act(0, {"type": "ox", "choice": "Z"}).error == "bad_input"
    assert sim.act(0, {"type": "ox", "choice": "o"}).error == "bad_input"
    assert sim.act(0, {"type": "ox"}).error == "bad_input"
    assert sim.act(0, {"type": "nope"}).error == "bad_input"
    assert sim.eng.phone_action(0, "x").error == "bad_input"
    assert sim.eng.phone_action(9, {"type": "ox", "choice": "O"}).error == "no_such_player"
    assert sim.act(0, {"type": "ox", "choice": "X"}).ok
    assert sim.act(0, {"type": "ox", "choice": "O"}).error == "already_answered"  # first pick is final
    v0, v1 = sim.eng.phone_view(0), sim.eng.phone_view(1)
    assert v0["screen"] == "ox_locked" and v0["own"] == {"pick": "X"}
    assert v1["screen"] == "ox" and v1["own"] == {"pick": None}  # Junho cannot see Mina's pick
    assert "X" not in json.dumps({k: v for k, v in v1.items() if k not in ("question",)}).replace('"Mina"', "")
    assert sim.of("ox.submitted")[-1]["data"] == {"seat": 0}
    assert v1["game"]["deadline"] == sim.eng.deadline  # countdown comes from server time
    assert v1["game"]["serverTime"] == sim.clock.now_ms()


def test_picks_outside_the_answer_window_are_rejected():
    sim = new_sim(BANK, names=("Mina",), seed=3)
    assert sim.act(0, {"type": "ox", "choice": "O"}).error == "not_now"
    sim.until_phase("ox.presenting")
    assert sim.act(0, {"type": "ox", "choice": "O"}).error == "not_now"
    sim.until_phase("ox.revealing_choices") if False else None


def test_early_finish_ignores_disconnected_players_but_waits_when_nobody_is_connected():
    sim = ox_sim(("Mina", "Junho"))
    sim.eng.phone_connection(1, False)
    t = sim.clock.now_ms()
    sim.act(0, {"type": "ox", "choice": "O"})
    sim.run(1_000)
    assert sim.eng.phase != "ox.answering"  # Mina was the only connected player: no waiting for the dropped phone
    sim2 = ox_sim(("Mina", "Junho"))
    sim2.eng.phone_connection(0, False)
    sim2.eng.phone_connection(1, False)
    t2 = sim2.clock.now_ms()
    sim2.until_type("answer.revealed")
    assert sim2.clock.now_ms() - t2 >= 20_000  # nobody connected: the whole window


def test_screen_progression_through_the_show():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=3)
    seen = set()
    sim.hooks.append(lambda s: seen.add(s.eng.phone_view(0)["screen"]))
    Bots(sim, ox=lambda s, q: "O" if s == 0 else "X", buzz=lambda q, l: 0 if q == 4 else None,
         voice=lambda q, s, n: ("mirror", "clear", True) if q == 4 else None, bet=lambda s, sc: sc, choice=lambda s: "B")
    sim.until_ended()
    assert {"waiting", "ox", "ox_locked", "buzzer", "answer_voice", "bet", "bet_locked", "final_choice", "final_locked", "done"} <= seen


# ---------------------------------------------------------------- betrayal actions
def test_betrayal_actions_only_for_the_target_in_the_right_step_with_valid_values():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=3)
    Bots(sim, ox=lambda s, q: {1: "O", 2: "X", 3: "O"}[q], reason=lambda s: None, decision=lambda s: None)
    sim.until_type("betrayal.listening")
    t = sim.eng.round.betrayal.seat  # 1
    other = 1 - t
    assert sim.act(other, {"type": "betrayal_reason", "reason": "knew"}).error == "not_now"
    assert sim.act(t, {"type": "betrayal_reason", "reason": "because"}).error == "bad_input"
    assert sim.act(t, {"type": "betrayal_decision", "switch": True}).error == "not_now"  # wrong step
    v = sim.eng.phone_view(t)
    assert v["screen"] == "betrayal_reason" and [r["id"] for r in v["own"]["betrayal"]["reasons"]] == list(BETRAYAL_REASONS)
    assert sim.eng.phone_view(other)["screen"] == "waiting" and "betrayal" not in sim.eng.phone_view(other)["own"]
    assert sim.act(t, {"type": "betrayal_reason", "reason": "knew"}).ok
    assert sim.act(t, {"type": "betrayal_reason", "reason": "hunch"}).error in ("not_now", "already_answered")
    sim.run_until(lambda: sim.eng.round.betrayal.step == "decision", what="decision step")
    assert sim.act(t, {"type": "betrayal_decision", "switch": "yes"}).error == "bad_input"
    assert sim.act(t, {"type": "betrayal_decision", "switch": 1}).error == "bad_input"
    assert sim.act(t, {"type": "betrayal_decision", "switch": True}).ok
    sim.until_type("betrayal.decided")
    assert sim.of("betrayal.decided")[0]["data"]["changed"] is True
    sim.run(1_000)  # the reaction cue starts after the stage acks the gate
    cue = [e for _, e, _ in sim.mc_fx if getattr(e, "cue", "") == "react_betrayal"][0]
    assert cue.facts["reason"] == "I KNEW IT" and cue.facts["changed"] is True


def test_betrayal_by_voice():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=3)
    Bots(sim, ox=lambda s, q: {1: "O", 2: "X", 3: "O"}[q], reason=lambda s: None, decision=lambda s: None)
    sim.until_type("betrayal.listening")
    l = sim.last_listen("reason")
    assert sim.eng.mc_voice_reason("l-bogus", "hello") is False
    assert sim.eng.mc_voice_reason(l.listen_id, "   ") is False
    assert sim.eng.mc_voice_reason(l.listen_id, "나는 알았어요") is True
    sim.run_until(lambda: sim.last_listen("decision") is not None, what="decision listen")
    d = sim.last_listen("decision")
    assert sim.eng.mc_voice_decision(d.listen_id, None) is False  # unclear: keep listening
    assert sim.eng.mc_voice_decision(d.listen_id, False) is True
    sim.pump()
    sim.until_type("betrayal.decided")
    assert sim.of("betrayal.decided")[0]["data"]["changed"] is False
    sim.run(1_000)  # the reaction cue starts after the stage acks the gate
    cue = [e for _, e, _ in sim.mc_fx if getattr(e, "cue", "") == "react_betrayal"][0]
    assert cue.facts["reason"] == "나는 알았어요"


# ---------------------------------------------------------------- final bets
@pytest.mark.parametrize("amount", [True, False, -1, 5.5, 5.0, "50", None, [5], 121, 10**9])
def test_invalid_bets_are_rejected(amount):
    sim = final_sim(bets={0: None, 1: None, 2: None})
    sim.until_phase("final.betting")
    assert sim.act(0, {"type": "bet", "amount": amount}).error == "bad_input"
    assert 0 not in sim.eng.round.bet_placed


def test_bet_limits_duplicates_and_own_view():
    sim = final_sim(bets={0: None, 1: None, 2: None})
    sim.until_phase("final.betting")
    assert sim.act(0, {"type": "bet", "amount": 120}).ok  # exactly the score
    assert sim.act(0, {"type": "bet", "amount": 5}).error == "already_answered"
    assert sim.act(1, {"type": "bet", "amount": 0}).ok  # zero is valid
    v0, v1, v2 = (sim.eng.phone_view(s) for s in (0, 1, 2))
    assert v0["screen"] == "bet_locked" and v0["own"]["bet"] == 120 and v0["own"]["maxBet"] == 120
    assert v2["screen"] == "bet" and v2["own"]["bet"] is None
    assert "120" not in json.dumps(v2["own"]) and sim.of("final.bet_placed")[-1]["data"] == {"seat": 1}
    assert sim.act(0, {"type": "final_choice", "choice": "A"}).error == "not_now"  # betting phase


def test_missing_bet_is_zero_and_zero_at_zero_is_all_in():
    sim = final_sim(bets={0: 30, 1: None, 2: None}, scores={0: 120, 1: 200, 2: 0}, choices={0: "B", 1: "B", 2: "B"})
    sim.until_ended()
    revs = {m["data"]["seat"]: m["data"] for m in sim.of("final.bet_revealed")}
    assert revs[1] == {"seat": 1, "bet": 0, "allIn": False, "remaining": 200}
    assert revs[2] == {"seat": 2, "bet": 0, "allIn": True, "remaining": 0}
    assert [m["data"]["seat"] for m in sim.of("final.bet_revealed")] == [2, 0, 1]
    final = sim.of("score.settled")[-1]["data"]["deltas"]
    assert [(d["seat"], d["delta"], d["score"]) for d in final] == [(0, 30, 150), (1, 0, 200), (2, 0, 0)]


def test_wrong_and_missing_answers_lose_the_bet_and_never_go_negative():
    sim = final_sim(bets={0: 120, 1: 200, 2: 80}, choices={0: "A", 1: None, 2: "C"})
    sim.until_ended()
    deltas = sim.of("score.settled")[-1]["data"]["deltas"]
    assert [(d["delta"], d["score"]) for d in deltas] == [(-120, 0), (-200, 0), (-80, 0)]
    assert all(p.score >= 0 for p in sim.eng.players.values())
    ch = sim.of("final.choices_revealed")[0]["data"]["choices"]
    assert ch == [{"seat": 0, "choice": "A"}, {"seat": 1, "choice": None}, {"seat": 2, "choice": "C"}]
    res = sim.of("answer.revealed")[-1]["data"]["results"]
    assert [r["correct"] for r in res] == [False, False, False]


def test_tie_for_the_win_and_shared_ranks():
    sim = final_sim(bets={0: 0, 1: 0, 2: 0}, scores={0: 100, 1: 100, 2: 40}, choices={0: "B", 1: "B", 2: "B"})
    sim.until_ended()
    w = sim.of("finale.winner")[0]["data"]
    assert w["winners"] == [0, 1] and w["tie"] is True
    assert [(f["seat"], f["rank"]) for f in w["finalScores"]] == [(0, 1), (1, 1), (2, 3)]
    r = sim.of("finale.results")[0]["data"]
    assert r["winners"] == [0, 1] and r["tie"] is True and [s["winner"] for s in r["standings"]] == [True, True, False]
    assert [s["seat"] for s in r["standings"]] == [0, 1, 2]


def test_solo_finale():
    sim = final_sim(names=("Mina",), bets={0: 50}, scores={0: 60}, choices={0: "B"})
    sim.until_ended()
    r = sim.of("finale.results")[0]["data"]
    assert r["mode"] == "solo" and r["winners"] == [0] and r["tie"] is False and len(r["standings"]) == 1
    assert sim.of("show.opening")[0]["data"]["mode"] == "solo"


# ---------------------------------------------------------------- settlement
def test_settlement_exactly_once_per_question_and_scores_add_up():
    sim = new_sim(BANK, names=("Mina", "Junho", "Ray"), seed=2)
    Bots(sim, ox=lambda s, q: "O" if s == 0 else "X", buzz=lambda q, l: 0 if q in (4, 6, 7) else None,
         voice=lambda q, s, n: ({4: "mirror", 6: "pumpkin", 7: "nope"}.get(q, "x"), "clear", True),
         bet=lambda s, sc: sc // 2, choice=lambda s: "B")
    sim.until_ended()
    settled = sim.of("score.settled")
    assert len(settled) == 8
    revealed = [m["data"]["questionId"] for m in sim.of("answer.revealed")]
    assert len(revealed) == len(set(revealed)) == 8
    total = {s: 0 for s in sim.eng.players}
    for m in settled:
        for d in m["data"]["deltas"]:
            total[d["seat"]] += d["delta"]
            assert d["score"] == total[d["seat"]]
    assert {s: p.score for s, p in sim.eng.players.items()} == total
    with pytest.raises(RuntimeError, match="already settled"):
        sim.eng.settle(sim.eng.content.questions[0], {0: 10})  # a second settlement of a question is refused
    q8 = sim.eng.content.questions[7]
    with pytest.raises(RuntimeError):
        sim.eng.settle(q8, {0: 1})


def test_points_per_kind():
    sim = new_sim(BANK, names=("Mina",), seed=2)
    Bots(sim, ox=lambda s, q: "O", buzz=lambda q, l: 0 if q in (4, 5, 6, 7) else None,
         voice=lambda q, s, n: ({4: "mirror", 5: "danse macabre", 6: "pumpkin", 7: "broomstick"}[q], "clear", True),
         bet=lambda s, sc: 10, choice=lambda s: "B")
    sim.until_ended()
    deltas = [m["data"]["deltas"][0]["delta"] for m in sim.of("score.settled")]
    # OX: Q1 O correct (+10), Q2 O correct (+10), Q3 answer X (0); buzzers +20 each; final +bet
    assert deltas == [10, 10, 0, 20, 20, 20, 20, 10]
