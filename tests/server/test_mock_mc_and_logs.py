"""The mock MC's contract, and what the server writes to its logs."""
import asyncio
import logging

import pytest

from khqs.content.dev_bank import build_dev_bank
from khqs.engine.effects import CUE_FACTS, McInterrupt, McSay
from khqs.mc.mock import MAX_MS, MIN_MS, MockMc, line_for
from khqs.server.host import GameHost
from khqs.server.runner import _config
from conftest import make_settings
from fasthost import FastHost

SAMPLE = {"names": ["Mina", "Ray"], "mode": "competitive", "act": 1, "title": "Act 1 · O/X", "number": 4, "category": "C",
          "text": "Some question text here", "resume": False, "level": 1, "max_level": 2, "clue": "A clue.", "kind": "ox",
          "name": "Mina", "choice": "O", "changed": True, "from": "O", "to": "X", "reason": "I KNEW IT", "answer": "O",
          "explanation": "Because.", "results": [], "correct": True, "attempt": 2, "scores": [], "choices": ["a", "b", "c", "d"],
          "winners": ["Mina"], "tie": False, "standings": []}


@pytest.mark.parametrize("cue", sorted(CUE_FACTS))
def test_every_cue_has_an_english_line(cue):
    facts = {k: SAMPLE[k] for k in CUE_FACTS[cue]}
    line = line_for(cue, facts)
    assert line and line.isascii() or "·" in line  # English text (the act title carries a middle dot)


def run(coro):
    return asyncio.run(coro)


def test_say_is_played_after_a_duration_and_an_interrupt_cancels_pending_lines():
    async def main():
        s = make_settings(mock_speed=20.0)
        host = GameHost(s, build_dev_bank(s.media_dir))
        host.start_pump()
        host.join("Mina")
        host.start()
        await asyncio.sleep(0.2)
        g = host.engine.gate
        host.run(host.engine.stage_hello, "c1", "primary", None)
        host.run(host.engine.stage_message, "c1", {"type": "stage.beat_done", "data": {"gate": g.id, "sseq": g.sseq}})
        await asyncio.sleep(0.05)
        assert host.engine._live, "the greeting was issued"
        tok = next(iter(host.engine._live))
        assert tok in host.mc._pending
        host.mc.handle(McInterrupt("test"))
        assert host.mc._pending == {}
        host.engine.interrupt_mc("test")
        await asyncio.sleep(0.2)
        assert host.engine.phase == "opening" and host.engine._live == set()  # a cancelled line never reports "played"
        await host.stop()
    run(main())


def test_durations_are_bounded_and_speed_scales_them():
    class H:  # minimal host for the duration helper
        engine = None
    m = MockMc(H(), speed=1.0)
    assert m.duration_ms("suspense", {}, "x") == MIN_MS
    assert m.duration_ms("read_final", {"text": "y" * 5000}, "x") == MAX_MS
    assert MockMc(H(), speed=2.0).duration_ms("suspense", {}, "x") == MIN_MS / 2


def test_captions_from_the_mock_pass_the_filter_and_buzzer_readings_are_never_captioned():
    async def main():
        s = make_settings(mock_speed=50.0, seed=3)
        host = FastHost(s, build_dev_bank(s.media_dir))
        host.start_pump()
        host.join("Mina")
        host.start()
        host.run(host.engine.stage_hello, "c1", "primary", None)
        deadline = asyncio.get_running_loop().time() + 30
        acked = set()
        while asyncio.get_running_loop().time() < deadline and host.engine.phase != "ended":
            g = host.engine.gate
            if g is not None and g.id not in acked:
                acked.add(g.id)
                host.run(host.engine.stage_message, "c1", {"type": "stage.beat_done", "data": {"gate": g.id, "sseq": g.sseq}})
            await asyncio.sleep(0.01)
            q = host.engine.q
            if q and q.kind == "buzzer" and host.engine.phase == "buzzer.open":
                break  # a buzzer question has been read: enough to look at its captions
        assert host.engine.phase == "buzzer.open", host.engine.phase
        stream = host.engine.stream
        caps = [m for m in stream if m["type"] == "mc.caption"]
        assert caps and all(c["data"]["final"] for c in caps)
        read_buzzer = [line for cue, line in host.mc.log if cue == "read_buzzer"]
        assert read_buzzer and not [c for c in caps if "Listen carefully" in c["data"]["text"]]
        await host.stop()
    run(main())


def test_no_access_log_and_server_logs_carry_no_names_or_credentials(caplog):
    cfg = _config(object(), "127.0.0.1", 1)
    assert cfg.access_log is False
    caplog.set_level(logging.DEBUG)
    from khqs.server.runner import RunningServer
    import net
    srv = RunningServer(make_settings()).start()
    try:
        st, body = net.post(f"http://127.0.0.1:{srv.settings.stage_port}/api/join", {"name": "Zoltán"})
        cred = body["credential"]
        net.post(f"http://127.0.0.1:{srv.settings.stage_port}/api/start", {})
        net.get(f"http://127.0.0.1:{srv.settings.stage_port}/")
    finally:
        srv.stop()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "Zoltán" not in text and cred not in text
    assert "phase=" in text and "listening stage=" in text
