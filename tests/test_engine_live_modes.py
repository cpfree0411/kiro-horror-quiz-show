"""Engine support for the live MC: playback-driven status, an offline MC, the mic interlock."""
from khqs.engine.effects import McSay
from support.content_fixture import BANK
from support.harness import Sim


def sim_live(**kw):
    s = Sim(BANK, status_from_playback=True, **kw)
    s.join("Mina")
    s.start()
    return s


def test_speaking_follows_mc_started_and_idle_follows_played():
    sim = sim_live(say_ms=10_000_000)
    sim.run_until(lambda: any(isinstance(e, McSay) for _, e, _ in sim.mc_fx), what="greeting")
    tok = next(e.token for _, e, _ in sim.mc_fx if isinstance(e, McSay))
    assert not [m for m in sim.stream if m["type"] == "mc.status"]  # issuing a line does not make the ghost talk
    assert sim.eng.mc_started("t-999") is False
    assert sim.eng.mc_started(tok) is True
    sim.pump()
    assert sim.of("mc.status")[-1]["data"] == {"status": "speaking"}
    sim.eng.mc_played(tok)
    sim.pump()
    assert sim.of("mc.status")[-1]["data"] == {"status": "idle"}
    assert sim.eng.mc_started(tok) is False  # a played line cannot start again


def test_default_engine_still_speaks_at_issue_time_for_the_mock():
    sim = Sim(BANK)
    sim.join("Mina"); sim.start()
    sim.run_until(lambda: sim.of("mc.status"), what="status")
    assert sim.of("mc.status")[0]["data"] == {"status": "speaking"}


def test_mc_offline_ends_pending_lines_and_later_lines_resolve_at_once():
    sim = sim_live(say_ms=10_000_000)
    sim.run_until(lambda: any(isinstance(e, McSay) for _, e, _ in sim.mc_fx), what="greeting")
    assert sim.eng._live
    sim.eng.mc_offline()
    sim.pump()
    assert not sim.eng._live and not sim.eng.mc_enabled and not sim.eng.voice_input
    n = len([1 for _, e, _ in sim.mc_fx if isinstance(e, McSay)])
    sim.until_type("act.started")
    assert len([1 for _, e, _ in sim.mc_fx if isinstance(e, McSay)]) == n  # no further MC commands
    sim.eng.mc_online(True)
    assert sim.eng.mc_enabled and sim.eng.voice_input
