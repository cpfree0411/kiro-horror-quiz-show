"""Time windows (rules section 4) and gate timeouts: the public deadline equals the real one."""
from khqs.engine.config import EngineConfig
from support.bots import Bots
from support.content_fixture import BANK
from support.flows import final_sim
from support.harness import new_sim


def deadline_of(sim, phase, nth=0):
    ms = [(m, t) for m, t in zip(sim.stream, sim.stream_t) if m["type"] == "phase.changed" and m["data"]["phase"] == phase]
    m, t = ms[nth]
    return m["data"]["deadline"], t


def test_default_windows_are_the_rules_table():
    c = EngineConfig()
    assert (c.ox_answer_ms, c.betrayal_input_ms, c.prompt_failsafe_ms, c.buzzer_open_ms, c.music_open_ms) == \
           (20_000, 8_000, 15_000, 15_000, 10_000)
    assert (c.media_interrupt_wait_ms, c.media_watchdog_extra_ms, c.final_bet_ms, c.final_answer_ms, c.gate_grace_ms) == \
           (800, 1_000, 20_000, 20_000, 25_000)
    assert c.buzzer_answer_ms == 20_000  # mock default; the live MC configures 60_000


def test_gate_timeouts_follow_the_interface_table():
    c = EngineConfig()
    expect = {"show.opening": 60000, "act.started": 8000, "question.presented": 5000, "ox.choices_revealed": 6000,
              "betrayal.offered": 6000, "betrayal.decided": 6000, "answer.revealed": 5000, "score.settled": 5000,
              "buzzer.judged": 5000, "av.hint": 5000, "final.category": 6000, "final.choices_revealed": 7000,
              "final.bet_revealed": 6000, "finale.winner": 12000, "finale.results": 15000}
    assert {k: c.gate_timeout(k) for k in expect} == expect
    assert c.gate_timeout("act.started", "3") == 10000 and c.gate_timeout("answer.revealed", "final") == 7000
    assert c.gate_timeout("score.settled", "final") == 7000 and c.gate_timeout("question.presented", "buzzer") == 5000


def test_ox_window_is_20s_and_the_public_deadline_is_real():
    sim = new_sim(BANK, names=("Mina",), seed=1)
    sim.until_phase("ox.answering")
    dl, t = deadline_of(sim, "ox.answering")
    assert dl == t + 20_000
    t0 = sim.clock.now_ms()
    sim.until_phase("ox.suspense")  # nobody answered: the empty reveal is skipped
    assert sim.clock.now_ms() - t0 == 20_000  # the whole window, to the millisecond


def test_final_windows_are_20s_each_and_end_early_when_everyone_is_in():
    sim = final_sim(bets={0: None, 1: None, 2: None}, choices={0: None, 1: None, 2: None})
    sim.until_phase("final.betting")
    dl, t = deadline_of(sim, "final.betting")
    assert dl == t + 20_000
    sim.until_phase("final.answering")
    dl2, t2 = deadline_of(sim, "final.answering")
    assert dl2 == t2 + 20_000 and t2 - t >= 20_000
    sim2 = final_sim()
    sim2.until_type("final.bets_locked")
    t_b = [t for m, t in zip(sim2.stream, sim2.stream_t) if m["type"] == "phase.changed" and m["data"]["phase"] == "final.betting"][-1]
    assert sim2.clock.now_ms() - t_b < 5_000  # all three bet quickly: no waiting for the deadline


def test_config_can_set_the_live_buzzer_window():
    sim = new_sim(BANK, names=("Mina",), seed=3, cfg=EngineConfig(buzzer_answer_ms=60_000))
    Bots(sim, ox=lambda s, q: "O", buzz=lambda q, l: 1 if q == 4 else None)
    sim.until_phase("buzzer.answering")
    dl, t = deadline_of(sim, "buzzer.answering")
    assert dl == t + 60_000


def test_viewers_cannot_report_media_or_beats():
    sim = new_sim(BANK, names=("Mina",), start=False)
    sim.hello(conn="v", role="viewer")
    n = len(sim.directs)
    sim.stage_send("stage.media_ended", {"assetId": "a-3f9c1d2e7b40", "level": 0, "reason": "ended", "positionSec": 20.0}, conn="v")
    sim.stage_send("stage.beat_done", {"gate": "g-1", "sseq": 1}, conn="v")
    sim.stage_send("stage.media_ready", {"assetIds": ["a-3f9c1d2e7b40"]}, conn="v")
    assert len(sim.directs) == n and not sim.eng.media_ready
