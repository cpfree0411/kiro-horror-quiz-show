"""Music question edge cases: interrupt fallback, stale media ends, watchdog, hint levels, mic gate."""
from khqs.engine.effects import McListen, McMic, McSay
from support.bots import Bots
from support.content_fixture import BANK
from support.harness import new_sim
from support.seeds import seed_for_track

ASSET = "a-3f9c1d2e7b40"


def music_sim(names=("Mina", "Junho"), auto_media=False, **kw):
    sim = new_sim(BANK, names=names, seed=seed_for_track("dm"), **kw)
    sim.auto_media = auto_media
    Bots(sim, ox=lambda s, n: "O" if s == 0 else "X")
    sim.until_type("av.play")
    return sim


def end(sim, **over):
    d = {"assetId": ASSET, "level": 0, "reason": "ended", "positionSec": 20.0}
    d.update(over)
    sim.stage_send("stage.media_ended", d)


def phases(sim):
    return [m["data"]["phase"] for m in sim.stream if m["type"] == "phase.changed"]


def test_buzz_without_media_ended_proceeds_after_exactly_800ms():
    sim = music_sim()
    t = sim.clock.now_ms()
    assert sim.act(1, {"type": "buzz"}).ok
    assert sim.of("buzzer.pressed")[-1]["data"] == {"seat": 1, "mediaInterrupted": True, "mcInterrupted": False}
    assert sim.eng.phase == "buzzer.media" and sim.eng.snapshot()["data"]["round"]["mediaPlaying"] is False
    sim.until_phase("buzzer.answering")
    assert sim.clock.now_ms() - t == 800
    end(sim, reason="interrupted", positionSec=13.0)  # a late confirmation changes nothing
    assert phases(sim)[-1] == "buzzer.answering"


def test_interrupt_confirmed_early_opens_the_answer_at_once():
    sim = music_sim()
    t = sim.clock.now_ms()
    sim.act(1, {"type": "buzz"})
    sim.run(100)
    end(sim, reason="interrupted", positionSec=13.0)
    assert sim.eng.phase == "buzzer.answering" and sim.clock.now_ms() - t == 100


def test_stale_or_wrong_media_ends_never_advance_and_natural_end_opens_10s_window():
    sim = music_sim()
    before = len(sim.stream)
    end(sim, level=1)  # wrong level
    end(sim, assetId="a-000000000000")  # wrong asset
    end(sim, positionSec=3.0)  # 'ended' far from the clip end
    end(sim, reason="interrupted", positionSec=13.0)  # nothing was interrupted
    end(sim, positionSec="x")
    assert len(sim.stream) == before and sim.eng.phase == "buzzer.media"
    t = sim.clock.now_ms()
    end(sim, positionSec=19.6)  # within tolerance
    op = sim.stream[-1]
    assert op["type"] == "phase.changed" and op["data"] == {"phase": "buzzer.open", "deadline": t + 10_000}
    n = len(sim.stream)
    end(sim)  # duplicate natural end
    assert len(sim.stream) == n
    assert sim.mic_fx[-1].open is True and sim.mic_fx[-2].open is False


def test_watchdog_covers_a_missing_end():
    sim = music_sim()
    t = sim.clock.now_ms()
    sim.until_phase("buzzer.open")
    assert sim.clock.now_ms() - t == 8_000 + 1_000  # clip length + 1 s


def test_stage_error_end_is_treated_as_an_end():
    sim = music_sim()
    end(sim, reason="error", positionSec=0.0)
    assert sim.eng.phase == "buzzer.open"


def test_buzz_in_open_window_after_the_clip_is_not_a_media_interrupt():
    sim = music_sim()
    end(sim)
    sim.act(0, {"type": "buzz"})
    assert sim.of("buzzer.pressed")[-1]["data"]["mediaInterrupted"] is False
    assert sim.eng.phase == "buzzer.answering"  # no interrupt wait: the clip was already over


def test_nobody_buzzes_goes_through_both_hints_then_suspense_and_reveal_with_credit():
    sim = music_sim(auto_media=True)
    sim.until_type("score.settled", 5)
    plays = [m["data"] for m in sim.of("av.play")]
    assert [(p["level"], p["startSec"], p["endSec"]) for p in plays] == [(0, 12.0, 20.0), (1, 0.0, 16.0), (2, 0.0, 30.0)]
    assert [m["data"]["level"] for m in sim.of("av.hint")] == [1, 2]
    lines = [e.facts for _, e, _ in sim.mc_fx if isinstance(e, McSay) and e.cue == "longer_listen"]
    assert lines == [{"level": 1, "max_level": 2}, {"level": 2, "max_level": 2}]  # one short line per step, never a clue
    assert not [e for _, e, _ in sim.mc_fx if isinstance(e, McSay) and e.cue.startswith("hint_")]
    ph = phases(sim)
    k = len(ph) - 1 - ph[::-1].index("buzzer.hint")
    assert "buzzer.suspense" in ph[k:] and ph.index("buzzer.suspense", k) > k
    rev = [m for m in sim.of("answer.revealed") if m["data"]["questionId"] == "q-av-05"][0]
    assert rev["data"]["results"] == [] and rev["data"]["credit"]["title"] == "Danse macabre"
    qs = [m["data"]["question"] for m in sim.of("question.presented") if m["data"]["question"]["kind"] == "av"]
    assert qs[0]["hintLevel"] == 0 and qs[0]["maxHintLevel"] == 2
    # mic: closed at each of the three plays, reopened after each end
    assert [e.open for e in sim.mic_fx][:6] == [False, True, False, True, False, True]


def test_no_mc_commands_between_av_play_and_the_end_of_each_clip():
    sim = music_sim(auto_media=True)
    sim.until_type("score.settled", 5)
    times = [(t, m) for m, t in zip(sim.stream, sim.stream_t) if m["type"] in ("av.play", "phase.changed")]
    windows = []
    start = None
    for t, m in times:
        if m["type"] == "av.play":
            start = t
        elif start is not None and m["data"]["phase"] == "buzzer.open":
            windows.append((start, t))
            start = None
    assert len(windows) == 3
    for a, b in windows:
        assert not [1 for _, e, t in sim.mc_fx if isinstance(e, (McSay, McListen)) and a < t < b]


def test_eligibility_is_per_level_and_lockouts_return_after_a_hint():
    sim = music_sim(auto_media=True)
    sim.act(1, {"type": "buzz"})
    sim.run(500)
    l = sim.last_listen("answer")
    sim.eng.mc_voice_answer(l.listen_id, "moonlight sonata", "clear", True)
    sim.pump()
    sim.until_type("av.hint")
    assert sim.eng.snapshot()["data"]["round"]["lockedOut"] == []
    assert sim.eng.snapshot()["data"]["round"]["attempts"] == [{"seat": 1, "correct": False}]
    sim.until_type("av.play", 2)
    sim.run_until(lambda: sim.eng.phase == "buzzer.open", what="open after level 1")
    assert sim.act(1, {"type": "buzz"}).ok  # seat 1 may buzz again at the new level
