"""Scenario themes 1 and 2: solo opening, duo act 1 with the betrayal chance."""
from khqs.engine.effects import McSay
from support import scenarios as sc
from support.bots import Bots
from support.content_fixture import BANK
from support.harness import Sim, new_sim

KEYS = {
    "ox.choices_revealed": ["choices"], "ox.unanimous": ["choice", "streak"],
    "betrayal.offered": ["seat", "selection", "currentChoice", "tiedSeats"],
    "betrayal.decided": ["seat", "from", "to", "changed"],
    "answer.revealed": ["questionId", "answer", "answerText", "results", "credit"],
    "score.settled": ["deltas", "leadChange"],
    "question.presented": ["question"],
}


def test_solo_lobby_opening_matches_scenario_and_greets_only_after_mc_ready():
    sim = Sim(BANK)
    assert sim.join("Mina").ok
    assert sim.start().ok
    sim.until_type("act.started")
    scn = sc.load("solo-lobby-opening")
    diffs = sc.compare(
        sim.stream, scn, ignore=("mc.status",),
        keys={"show.opening": ["mode"], "act.started": ["act", "title", "questionCount", "assets"]},
        # intended: the new game opens with phase.changed lobby (sseq 1); the scenario's fan/seat differ (see below)
        skip_engine=lambda m: m["type"] == "phase.changed" and m["data"]["phase"] == "lobby",
        skip_scenario=lambda m: False,
    )
    assert diffs == [], diffs  # a solo player is centred (seat 1), exactly as in the scenario
    op = sim.of("show.opening")[0]
    assert op["data"]["mode"] == "solo" and op["data"]["seats"][1]["player"]["name"] == "Mina"
    assert [s["status"] for s in op["data"]["seats"]] == ["vacant", "occupied", "vacant"]
    assert op["gate"]["timeoutMs"] == 60000
    # MC_READY: the greeting is cued only after the stage acked the opening gate
    ack_t = next(t for m, t in zip(sim.stream, sim.stream_t) if m["type"] == "show.opening") + sim.ack_ms
    greet = [(t, e) for _, e, t in sim.mc_fx if isinstance(e, McSay) and e.cue == "greeting"]
    assert len(greet) == 1 and greet[0][0] >= ack_t
    assert greet[0][1].facts == {"names": ["Mina"], "mode": "solo"}


def test_duo_act1_betrayal_matches_scenario():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=3)  # seed 3: Mina=sack, Junho=bolt, tie pick = Junho (as in the scenario)
    Bots(sim, ox=lambda s, q: {1: "O", 2: "X", 3: "O"}[q], decision=lambda seat: True)
    sim.until_type("score.settled", 2)
    scn = sc.load("duo-act1-ox-betrayal")
    i_end = max(i for i, m in enumerate(scn) if m["type"] == "score.settled")
    stream = sim.stream[: next(i for i, m in enumerate(sim.stream) if m["type"] == "score.settled" and m["sseq"] == sim.of("score.settled")[1]["sseq"]) + 1]
    diffs = sc.compare(
        stream, scn[: i_end + 1], ignore=("mc.status",), keys=KEYS,
        skip_engine=lambda m: m["type"] in ("seat.joined", "show.opening")
        or (m["type"] == "phase.changed" and m["data"]["phase"] in ("lobby", "opening", "act_intro")),
        skip_scenario=lambda m: m["type"] == "snapshot",
    )
    assert diffs == [], diffs
    off = sim.of("betrayal.offered")[0]["data"]
    assert off == {"seat": 1, "selection": "tied_random", "currentChoice": "X", "tiedSeats": [0, 1]}
    assert sim.of("betrayal.decided")[0]["data"] == {"seat": 1, "from": "X", "to": "O", "changed": True}
    deltas = sim.of("score.settled")[1]["data"]
    assert deltas["leadChange"] is True and [d["score"] for d in deltas["deltas"]] == [10, 20]


def test_betrayal_timeout_keeps_the_pick_and_never_says_last():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=3)
    Bots(sim, ox=lambda s, q: {1: "O", 2: "X", 3: "O"}[q], reason=lambda seat: None, decision=lambda seat: None)
    sim.until_type("betrayal.decided")
    d = sim.of("betrayal.decided")[0]["data"]
    assert d["changed"] is False and d["from"] == d["to"] == "X"
    # reason window 8 s + decision window 8 s were really waited
    t0 = next(t for m, t in zip(sim.stream, sim.stream_t) if m["type"] == "betrayal.listening")
    t1 = next(t for m, t in zip(sim.stream, sim.stream_t) if m["type"] == "betrayal.decided")
    assert t1 - t0 >= 16_000
    sim.until_ended()
    for _, e, _t in sim.mc_fx:
        if isinstance(e, McSay):
            blob = repr(e.facts).lower()
            assert "last" not in blob and "worst" not in blob and "loser" not in blob


def test_solo_never_unanimous_never_betrays():
    sim = new_sim(BANK, names=("Mina",))
    Bots(sim, ox=lambda s, q: "O")
    sim.until_type("score.settled", 3)
    assert not sim.of("ox.unanimous") and not sim.of("betrayal.offered")


def test_streak_resets_on_split_and_on_trigger():
    sim = new_sim(BANK, names=("Mina", "Junho", "Ray"), seed=2)
    # Q1 unanimous, Q2 split (streak resets), Q3 unanimous again: never reaches 2 in a row
    Bots(sim, ox=lambda s, q: {1: "O", 2: ("O" if s else "X"), 3: "O"}[q])
    sim.until_type("score.settled", 3)
    assert [m["data"]["streak"] for m in sim.of("ox.unanimous")] == [1, 1]
    assert not sim.of("betrayal.offered")


def test_missing_pick_breaks_unanimity_and_is_omitted():
    sim = new_sim(BANK, names=("Mina", "Junho"), seed=2)
    Bots(sim, ox=lambda s, q: None if (q == 1 and s == 1) else "O")
    sim.until_type("ox.choices_revealed")
    assert sim.of("ox.choices_revealed")[0]["data"]["choices"] == [{"seat": 0, "choice": "O"}]
    assert not sim.of("ox.unanimous")
    sim.until_type("answer.revealed")
    assert sim.of("answer.revealed")[0]["data"]["results"] == [{"seat": 0, "correct": True}, {"seat": 1, "correct": False}]


def test_nobody_answers_skips_the_empty_reveal():
    sim = new_sim(BANK, names=("Mina", "Junho"))
    Bots(sim, ox=lambda s, q: None)
    sim.until_type("answer.revealed")
    assert not sim.of("ox.choices_revealed") and not sim.of("ox.unanimous")
    assert sim.of("answer.revealed")[0]["data"]["results"] == [{"seat": 0, "correct": False}, {"seat": 1, "correct": False}]
