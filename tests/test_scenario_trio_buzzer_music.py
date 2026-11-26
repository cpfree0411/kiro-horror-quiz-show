"""Scenario theme 3: trio act 2 with an early wrong buzz, text after the reading, a music buzz that stops the
music, a hint and a longer replay. Act 1 is played so the scores are 30 / 20 / 10 as in the scenario."""
import pytest

from khqs.engine.effects import McInterrupt, McListen, McMic, McSay
from support import scenarios as sc
from support.bots import Bots
from support.content_fixture import BANK
from support.harness import new_sim
from support.seeds import seed_for_track

ACT1 = {1: {0: "O", 1: "O", 2: "X"}, 2: {0: "O", 1: "O", 2: "X"}, 3: {0: "X", 1: "O", 2: "X"}}
# Q1 answer O, Q2 O, Q3 X  ->  Mina 30, Junho 20, Ray 10 (never unanimous, so no betrayal)
VOICE = {(4, 2, 1): "Pillow", (4, 0, 1): "Mirror", (5, 1, 1): "Moonlight Sonata", (5, 0, 1): "Danse Macabre"}


def make():
    sim = new_sim(BANK, names=("Mina", "Junho", "Ray"), seed=seed_for_track("dm"),
                  say_ms={"read_buzzer": 3400, "intro_music": 2200, "*": 800})

    def buzz(q, level):
        e, r = sim.eng, sim.eng.round
        if q == 4:
            if e.phase == "buzzer.reading" and not r.attempts:
                return 2
            if e.phase == "buzzer.open":
                return 0
        if q == 5:
            if level == 0 and e.phase == "buzzer.media" and not r.attempts:
                return 1
            if level == 1 and e.phase == "buzzer.open":
                return 0
        return None

    bots = Bots(sim, ox=lambda s, q: ACT1[q][s], buzz=buzz, voice=lambda q, s, n: (VOICE[(q, s, n)], "clear", True),
                think_ms=2100)
    return sim, bots


SKIP_PHASES = ("buzzer.suspense", "buzzer.judging")
KEYS = {
    "act.started": ["act", "title", "questionCount"],
    "question.presented": ["question"], "question.text_revealed": ["questionId", "text"],
    "buzzer.pressed": ["seat", "mediaInterrupted", "mcInterrupted"], "buzzer.judged": ["seat", "correct"],
    "av.play": ["assetId", "level", "startSec", "endSec"], "av.hint": ["level", "media"],
    "answer.revealed": ["questionId", "answer", "answerText", "results"], "score.settled": ["deltas", "leadChange"],
    "buzzer.armed": ["questionId"],
}


def _act2(sim):
    first = next(i for i, m in enumerate(sim.stream) if m["type"] == "act.started" and m["data"]["act"] == 2)
    return sim.stream[first:]


def _drop_tail_phases(msgs):
    """The scenario's music tail omits two phase.changed messages (shorthand); drop them on both sides there."""
    k = max(i for i, m in enumerate(msgs) if m["type"] == "av.play")
    return msgs[: k + 1] + [m for m in msgs[k + 1:] if not (
        m["type"] == "phase.changed" and m["data"]["phase"] in ("buzzer.revealing_answer", "buzzer.settling"))]


def test_act2_matches_scenario():
    sim, _ = make()
    sim.until_type("score.settled", 5)  # 3 OX + 2 buzzer questions
    scn = sc.load("trio-act2-buzzer-music", {"q-av-02": "q-av-05"})
    diffs = sc.compare(
        _drop_tail_phases(_act2(sim)), _drop_tail_phases(scn), ignore=("mc.status", "buzzer.answer_heard", "snapshot"),
        keys=KEYS,
        # intended divergences (design.md section 9): an acknowledged suspense step before every buzzer reveal;
        # the judging phase is always sent (the scenario shows it once)
        skip_engine=lambda m: (m["type"] == "phase.changed" and m["data"]["phase"] in SKIP_PHASES) or m["type"] == "answer.suspense",
        skip_scenario=lambda m: m["type"] == "phase.changed" and m["data"]["phase"] in SKIP_PHASES,
    )
    assert diffs == [], diffs
    assert [sim.eng.players[s].score for s in (0, 1, 2)] == [70, 20, 10]


def test_buzzer_round_has_suspense_and_judging_before_every_verdict():
    sim, _ = make()
    sim.until_type("score.settled", 5)
    st = sim.types()
    for i, m in enumerate(sim.stream):
        if m["type"] == "buzzer.judged":
            assert sim.stream[i - 1] ["data"].get("phase") == "buzzer.judging"
        if m["type"] == "answer.revealed" and m["data"]["questionId"].startswith(("q-bz", "q-av")):
            prev = [x["type"] for x in sim.stream[i - 4: i]]
            assert "answer.suspense" in prev, prev


def test_early_buzz_cuts_the_mc_and_text_comes_only_after_the_reading_played():
    sim, _ = make()
    sim.until_type("question.text_revealed")
    pressed = sim.of("buzzer.pressed")[0]
    assert pressed["data"] == {"seat": 2, "mediaInterrupted": False, "mcInterrupted": True}
    says = [(s, e, t) for s, e, t in sim.mc_fx if isinstance(e, McSay) and e.cue == "read_buzzer"]
    assert len(says) == 2 and says[0][1].facts["resume"] is False and says[1][1].facts["resume"] is True
    assert says[0][1].token != says[1][1].token  # a fresh output token
    # interrupt happened between the buzz and the resumed reading
    kinds = [type(e).__name__ for _, e, _ in sim.mc_fx]
    assert "McInterrupt" in kinds
    t_rev = next(t for m, t in zip(sim.stream, sim.stream_t) if m["type"] == "question.text_revealed")
    assert t_rev >= says[1][2] + 3400  # revealed only after the resumed reading finished playing
    # the first reading's token is stale: a late `played` for it does nothing
    assert sim.eng.mc_played(says[0][1].token) is False
    # the text was hidden everywhere before that
    for m in sim.stream[: sim.stream.index(next(x for x in sim.stream if x["type"] == "question.text_revealed"))]:
        assert "never look into" not in repr(m)
    for snap in sim.snapshots:
        if snap["sseq"] < sim.of("question.text_revealed")[0]["sseq"]:
            assert "never look into" not in repr(snap)


def test_music_collision_rules_and_interrupt():
    sim, _ = make()
    sim.until_type("av.play", 2)
    play0 = sim.of("av.play")[0]
    t_play = sim.stream_t[sim.stream.index(play0)]
    pressed = [m for m in sim.of("buzzer.pressed") if m["data"]["mediaInterrupted"]]
    assert len(pressed) == 1 and pressed[0]["data"]["mcInterrupted"] is False
    t_press = sim.stream_t[sim.stream.index(pressed[0])]
    # mic closed before the clip, no MC command from av.play until the buzz
    assert [e.open for e in sim.mic_fx][:1] == [False]
    quiet = [e for s, e, t in sim.mc_fx if t_play <= t <= t_press and isinstance(e, (McSay, McListen))]
    assert quiet == []
    # the answer opens only after the stage confirmed the interrupt (100 ms in the fake stage)
    t_ans = next(t for m, t in zip(sim.stream, sim.stream_t) if m["type"] == "phase.changed"
                 and m["data"]["phase"] == "buzzer.answering" and m["sseq"] > pressed[0]["sseq"])
    assert t_ans >= t_press + 100
    # mic reopened for the answer
    assert any(e.open for e in sim.mic_fx)


def test_the_automatic_step_resets_eligibility_and_speaks_no_clue():
    sim, _ = make()
    sim.until_type("av.hint")
    hint = sim.of("av.hint")[0]["data"]
    assert hint["level"] == 1 and hint["media"] == {"assetId": "a-3f9c1d2e7b40", "mediaType": "audio"}
    sim.until_type("score.settled", 5)
    cue = [e for _, e, _ in sim.mc_fx if isinstance(e, McSay) and e.cue == "longer_listen"][0]
    assert cue.facts == {"level": 1, "max_level": 2}  # a longer listen only: no clue, no hint on the ladder
    assert not [e for _, e, _ in sim.mc_fx if isinstance(e, McSay) and e.cue.startswith("hint_")]
    assert "fiddle" not in repr(sim.stream)  # the clue never goes to the stage
    judged = sim.of("buzzer.judged")
    assert judged[-1]["data"] == {"seat": 0, "correct": True, "lockedOut": []}  # eligibility was reset (rules 6.1)


def test_credit_only_in_answer_revealed():
    sim, _ = make()
    sim.until_type("score.settled", 5)
    rev = [m for m in sim.of("answer.revealed") if m["data"]["questionId"] == "q-av-05"][0]
    assert rev["data"]["credit"]["title"] == "Danse macabre" and rev["data"]["credit"]["license"]
    before = sim.stream[: sim.stream.index(rev)]
    assert "Test Composer" not in repr(before) and "Test Orchestra" not in repr(before)
    for snap in sim.snapshots:
        if snap["sseq"] < rev["sseq"]:
            assert "Test Composer" not in repr(snap)
