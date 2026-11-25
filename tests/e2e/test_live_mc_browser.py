"""P3 acceptance (H2): a full solo game through the real browser audio host and /ws/mc, with a FAKE Live transport.

No API, no key, no session. The browser plays real PCM, reports real playback start/end and captures a (fake) microphone.
Slow. Run:  scripts/test.sh -m slow tests/e2e/test_live_mc_browser.py
"""
import subprocess
import time

import pytest
from playwright.sync_api import sync_playwright

from khqs.mc.transport import AudioOut, OutText, ToolCall, TurnComplete
from khqs.server.runner import RunningServer
from khqs.server.settings import Settings
from support.secrecy import assert_no_leaks
from driver import Show
from live_rig import FakeTransport, tone
from server_helpers import free_port

pytestmark = pytest.mark.slow


class TalkingTransport(FakeTransport):
    """About 1.2 s of audible tone per turn, in 300 ms chunks; the tool call is scripted by the test."""

    async def send_turn(self, text):
        self.turns.append(text)
        self.positions.append(self.sseq_now())
        for i in range(4):
            self.push(AudioOut(tone(300, 4000, 24000)))
        self.push(OutText("Words from the host."))
        self.push(TurnComplete())


def make_wav(path):
    """1.2 s of loud tone then 5 s of silence, looped by Chromium's fake capture device."""
    subprocess.run(["sox", "-n", "-r", "16000", "-c", "1", "-b", "16", str(path), "synth", "1.2", "sine", "440", "vol", "0.6", "pad", "0", "5"], check=True)


def test_full_solo_game_through_the_browser_audio_host(tmp_path):
    wav = tmp_path / "mic.wav"
    make_wav(wav)
    s = Settings(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True, record=True, seed=5,
                 mc="live", buzzer_answer_ms=40_000, join_grace_s=60.0).validate()
    srv = RunningServer(s).start()
    host = srv.host
    transports = []
    answers = {4: "Mirror"}  # question 4 is answered by (fake) voice; question 6 by typing

    def factory():
        t = TalkingTransport(transports)
        t.sseq_now = lambda: host.engine._sseq
        t.tool_script = lambda: [ToolCall("call-%d" % len(t.activities), "report_answer",
                                          {"heard": answers.get(host.engine.question_no, "nothing"), "recognition": "clear"})]
        return t
    host.mc.factory = factory
    try:
        with sync_playwright() as pw:
            show = Show(pw, srv, "live_mc", extra_args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                                       f"--use-file-for-fake-audio-capture={wav}"])
            try:
                show.open_stage()
                show.join_pad("Mina")
                # collapsed to an edge tab while nothing needs the pad player
                assert show.stage.locator("#khqs-padtab").is_visible() and not show.stage.locator("#khqs-pad").is_visible()
                show.start_show()
                show.stage.wait_for_function("document.querySelector('#khqs-chip').dataset.mc === 'online'", timeout=30000)
                assert host.mc.state == "online" and host.mc.sessions_opened == 1
                opened_pad = {"seen": False}

                def plan_tick(eng):
                    if show.stage.locator("#khqs-pad").is_visible():
                        opened_pad["seen"] = True
                plan = {
                    "ox": lambda seat, qn: "O", "buzz": lambda qn, attempts, phase: 1 if qn in (4, 6) and attempts == 0 else None,
                    "text": lambda qn, seat, attempts: "Pumpkin", "bet": lambda seat, score: score // 2, "final": lambda seat: "B",
                }
                typed = {"done": False}
                orig_tick = show.tick

                def tick(plan_):
                    orig_tick(plan_)
                    plan_tick(show.eng)
                    v = show.players[0].view()
                    # question 6: choose to type instead of speaking
                    if v and v["screen"] == "answer_voice" and show.eng.question_no == 6 and not typed["done"]:
                        typed["done"] = True
                        show.players[0].target.click("#type-instead")
                show.tick = tick
                show.play(plan)
                ev = show.finale_checks()
                eng = host.engine
                assert eng.phase == "ended" and eng.stats["gate_timeouts"] == 0
                assert show.errors == [], show.errors
                assert ev["pods"] >= 1 and ev["saw_new_show"] and not ev["early_new_show"]
                assert opened_pad["seen"], "the pad panel opened when its player had something to do"
                t = transports[0]
                # --- the playback cursor: every line the engine issued was reported played by the browser itself
                fx = host.recorder.mc_fx
                said = {e.token: (i, e.cue) for i, (_, e, _) in enumerate(fx) if e.__class__.__name__ == "McSay"}
                played = set(show.stage.evaluate("KHQS_MC.played"))
                started = set(show.stage.evaluate("KHQS_MC.started"))
                assert said and played <= set(said) and played <= started
                for tok in set(said) - played:  # a line never played must be one a buzz cut off mid-reading
                    i, cue = said[tok]
                    assert cue == "read_buzzer" and any(e.__class__.__name__ == "McInterrupt" for _, e, _ in fx[i:]), (tok, cue)
                assert len(played) >= len(said) - 4
                sts = [m["data"]["status"] for m in eng.stream if m["type"] == "mc.status"]
                assert "speaking" in sts and all(a != b for a, b in zip(sts, sts[1:]))
                # --- the mic: forwarded only for the voice answer, and the answer was judged from the tool call
                assert show.stage.evaluate("KHQS_MC.forwarded") > 5
                assert t.activities.count(True) >= 1 and t.activities.count(True) == t.activities.count(False)
                judged = [m for m in eng.stream if m["type"] == "buzzer.judged"]
                assert judged and judged[0]["data"]["correct"] is True  # "Mirror", reported by the (fake) model, judged locally
                assert [r for r in t.tool_results if r[2] != {"received": True}] == []
                assert not [m for m in eng.stream if m["type"] == "buzzer.answer_heard"]
                # --- one session, never reconnected; secrecy over everything sent to the model
                assert host.mc.sessions_opened == 1 and len(transports) == 1
                rec = host.recorder
                rec.mc_fx = list(rec.mc_fx) + [(pos, __import__("khqs.engine.effects", fromlist=["McSay"]).McSay("p", "x", {"prompt": txt}), 0)
                                               for pos, txt in zip(t.positions, t.turns)]
                assert_no_leaks(rec)
            finally:
                show.close()
    finally:
        srv.stop()
