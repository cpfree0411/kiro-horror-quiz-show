"""LiveMc against a fake Live transport. No network, no API key, no session is ever opened."""
import asyncio
import logging

import pytest

from khqs.engine.effects import McInterrupt, McListen, McSay
from khqs.mc import live as livemod
from khqs.mc.transport import AudioOut, GoAway, GeminiTransport, Interrupted, LiveError, ResumeHandle, ToolCall, TurnComplete, Closed
from live_rig import Rig, run, tone


def test_connect_one_session_status_follows_real_playback_and_gate_waits_for_it():
    async def main():
        rig = await Rig().up()
        assert rig.mc.state == "online" and rig.mc.sessions_opened == 1 and rig.eng.mc_enabled and rig.eng.voice_input
        rig.port.play_ms = 400
        with pytest.raises(LiveError):
            await rig.mc.connect()  # one live session at a time
        rig.host.join("Mina"); rig.host.start()
        await rig.until(lambda: rig.t.turns)
        assert rig.t.turns[0].startswith("[CUE greeting]") and "Mina" in rig.t.turns[0]
        assert rig.eng.mc_status != "speaking"  # generation alone does not make the ghost talk
        await rig.until(lambda: rig.port.ended)
        tok = rig.port.ended[0]
        assert tok in rig.eng._live and rig.eng.mc_status != "speaking"  # audio is queued in the browser, not yet playing
        await rig.until(lambda: rig.eng.mc_status == "speaking", timeout=3)
        assert tok in rig.eng._live  # still not played: the engine keeps waiting
        await rig.until(lambda: tok not in rig.eng._live, timeout=3)
        assert rig.eng.mc_status == "idle"
        sts = [m["data"]["status"] for m in rig.eng.stream if m["type"] == "mc.status"]
        assert sts[:2] == ["speaking", "idle"]
        await rig.down()
    run(main())


def test_interrupt_flushes_discards_old_audio_and_survives_interrupted_then_late_turn_complete():
    async def main():
        rig = Rig()
        rig.hold_next = True  # the reading never completes by itself
        await rig.up()
        rig.host.join("Mina"); rig.host.start()
        await rig.until(lambda: rig.t.turns)
        await rig.until(lambda: rig.port.audio_log)
        n_audio = len(rig.port.audio_log)
        flushes = rig.port.flushes
        rig.host.run(rig.mc.handle, McInterrupt("buzz"))
        assert rig.port.flushes == flushes + 1 and rig.mc.draining and rig.mc.current is None
        rig.t.push(AudioOut(tone(50, 3000, 24000)))  # old generation still talking: must not reach the browser
        rig.t.push(Interrupted())
        rig.t.push(TurnComplete())  # the late turn_complete after interrupted: normal, not an error
        await asyncio.sleep(0.1)
        assert len(rig.port.audio_log) == n_audio and rig.mc.state == "online"
        # the next line goes out only after the provider acknowledged, and is not completed by the late event
        rig.t.hold = False
        rig.host.run(rig.mc.handle, McSay("t-x", "ask_again", {"name": "Mina", "attempt": 2}))
        await rig.until(lambda: len(rig.t.turns) == 2)
        assert rig.t.turns[1].startswith("[CUE ask_again]") and not rig.mc.draining
        await rig.until(lambda: "t-x" in rig.port.ended)
        assert rig.mc.state == "online"
        await rig.down()
    run(main())


def buzz_to_answering(rig):
    """Play solo to the first buzzer question and buzz in (phone action); returns the engine's listen."""
    async def go():
        rig.host.join("Mina"); rig.host.start()
        await rig.until(lambda: rig.eng.phase == "ox.answering")
        for _ in range(3):
            await rig.until(lambda: rig.eng.phase == "ox.answering")
            rig.host.run(rig.eng.phone_action, 1, {"type": "ox", "choice": "O"})
            await rig.until(lambda: rig.eng.phase != "ox.answering")
        await rig.until(lambda: rig.eng.phase in ("buzzer.reading", "buzzer.open"))
        assert rig.host.run(rig.eng.phone_action, 1, {"type": "buzz"}).ok
        await rig.until(lambda: rig.mc.listen is not None and rig.mc.listen.mic_open, timeout=10)
    return go()


def test_mic_opens_only_for_a_listen_and_silence_never_reaches_live():
    async def main():
        rig = await Rig().up()
        assert rig.port.mic_log == []  # before any listen the mic is closed
        await buzz_to_answering(rig)
        assert rig.port.mic_log[-1] is True and rig.t.contexts and "report_answer" in rig.t.contexts[-1]
        for _ in range(30):
            await rig.mc.on_mic(tone(20, 20))  # near-silence
        assert rig.t.audio == [] and rig.t.activities == []
        l = rig.mc.listen
        await rig.mc.on_mic(tone(20, 20))
        # audio arriving with no listen open is dropped
        rig.host.run(rig.eng.stage_message, "c1", {"type": "stage.ping", "data": {"clientTime": 1}})
        await rig.down()
    run(main())


def test_spoken_answer_becomes_a_tool_call_with_silent_receipt_and_the_engine_judges():
    async def main():
        rig = await Rig().up()
        await buzz_to_answering(rig)
        l = rig.mc.listen
        rig.t.tool_script = lambda: [ToolCall("c-1", "report_answer", {"heard": "  Mirror  ", "recognition": "clear"})]
        for _ in range(12):
            await rig.mc.on_mic(tone(20, 8000))
        assert rig.t.activities == [True] and rig.t.audio  # activity starts only once voiced, with the held lead-in
        for _ in range(40):
            await rig.mc.on_mic(tone(20, 20))
            if rig.t.activities[-1:] == [False]:
                break
        assert rig.t.activities == [True, False] and rig.port.mic_log[-1] is False
        await rig.until(lambda: rig.eng.stream and any(m["type"] == "buzzer.judged" for m in rig.eng.stream))
        j = [m for m in rig.eng.stream if m["type"] == "buzzer.judged"][0]
        assert j["data"]["correct"] is True  # "Mirror" with the spaces stripped, judged locally
        assert rig.t.tool_results == [("c-1", "report_answer", {"received": True})]
        await rig.down()
    run(main())


def test_no_tool_call_or_no_voiced_audio_is_a_recognition_failure_never_a_wrong_answer(monkeypatch):
    monkeypatch.setattr(livemod, "TOOL_WAIT_S", 0.3)
    monkeypatch.setattr(livemod, "NO_SPEECH_S", 0.3)
    async def main():
        rig = await Rig().up()
        await buzz_to_answering(rig)
        # silence for the whole window: no Live traffic, engine asks again
        await rig.until(lambda: any(isinstance(e, McSay) and e.cue == "ask_again" for _, e, _ in rig.host.recorder.mc_fx), timeout=5)
        assert not [m for m in rig.eng.stream if m["type"] == "buzzer.judged"] and rig.t.activities == []
        # speech, then the model never calls the tool
        await rig.until(lambda: rig.mc.listen is not None and rig.mc.listen.mic_open and rig.mc.listen.attempt == 2, timeout=8)
        for _ in range(12):
            await rig.mc.on_mic(tone(20, 8000))
        for _ in range(40):
            await rig.mc.on_mic(tone(20, 20))
        await rig.until(lambda: rig.eng.round.text_box, timeout=5)  # second failure: the phone text box opens
        assert not [m for m in rig.eng.stream if m["type"] == "buzzer.judged"]
        await rig.down()
    run(main())


def test_a_tool_call_without_voiced_evidence_does_not_count():
    async def main():
        rig = await Rig().up()
        await buzz_to_answering(rig)
        l = rig.mc.listen
        # the model hallucinates an answer although nothing voiced was heard
        await rig.mc._on_tool(ToolCall("c-9", "report_answer", {"heard": "Mirror", "recognition": "clear"}))
        await asyncio.sleep(0.1)
        assert not [m for m in rig.eng.stream if m["type"] == "buzzer.judged"]
        assert rig.eng.round.failures == 1 and rig.t.tool_results[-1][2] == {"received": True}
        await rig.down()
    run(main())


def test_stale_or_wrong_tool_calls_get_a_silent_receipt_and_are_ignored():
    async def main():
        rig = await Rig().up()
        await rig.mc._on_tool(ToolCall("c-1", "report_answer", {"heard": "x", "recognition": "clear"}))  # no listen open
        await rig.mc._on_tool(ToolCall("c-2", "report_decision", {"decision": "switch"}))
        assert [r[2] for r in rig.t.tool_results] == [{"received": True}] * 2
        assert rig.mc.state == "online"
        await rig.down()
    run(main())


@pytest.mark.slow
def test_nothing_sent_to_the_model_leaks_a_secret_before_its_reveal_and_captions_are_filtered():
    from support.secrecy import assert_no_leaks
    from support.randbots import random_bots

    class Spy:
        pass

    async def main():
        rig = await Rig().up()
        rig.host.join("Mina"); rig.host.start()
        # a model that tries to blurt the answer of the current buzzer question in its transcription
        orig = rig.t.send_turn

        async def blurt(text):
            await orig(text)
            q = rig.eng.q
            if q and q.kind == "buzzer":
                rig.t.push(__import__("khqs.mc.transport", fromlist=["OutText"]).OutText(f" Psst, it is {q.answer}!"))
        rig.t.send_turn = blurt
        end = asyncio.get_running_loop().time() + 150
        while rig.eng.phase != "ended" and asyncio.get_running_loop().time() < end:
            rig.autoack()
            e = rig.eng
            r = e.round
            if e.phase == "ox.answering":
                rig.host.run(e.phone_action, 1, {"type": "ox", "choice": "O"})
            if e.phase in ("buzzer.open",) and r.holder is None and 1 not in r.locked:
                rig.host.run(e.phone_action, 1, {"type": "buzz"})
            if e.phase == "buzzer.answering" and r.holder == 1 and not r.text_box:
                rig.host.run(e.phone_action, 1, {"type": "choose_typing"})  # typing instead of speaking
            if e.phase == "buzzer.answering" and r.text_box:
                rig.host.run(e.phone_action, 1, {"type": "text_answer", "text": e.q.answer})
            if e.phase == "final.betting":
                rig.host.run(e.phone_action, 1, {"type": "bet", "amount": 0})
            if e.phase == "final.answering":
                rig.host.run(e.phone_action, 1, {"type": "final_choice", "choice": "B"})
            await asyncio.sleep(0.01)
        assert rig.eng.phase == "ended"
        # (1) every string handed to the transport, scanned like an MC command
        rec = rig.host.recorder
        rec.mc_fx = list(rec.mc_fx) + rig.turns_as_says_with_positions()
        assert_no_leaks(rec)
        # (2) tool results are only {"received": true}
        assert all(r[2] == {"received": True} for r in rig.t.tool_results)
        # (3) the blurted answers never reached the stage as captions
        caps = " ".join(m["data"]["text"] for m in rig.eng.stream if m["type"] == "mc.caption")
        for q in rig.eng.content.questions:
            if q.kind == "buzzer":
                assert f"it is {q.answer}" not in caps
        await rig.down()
    run(main())


# ---------------------------------------------------------------- caps, offline fallback, no automatic reconnect
def test_connect_failure_leaves_the_mc_offline_and_nothing_retries(monkeypatch):
    async def main():
        rig = Rig()
        rig.fail_connect = LiveError("could not open a Live session: APIError (429)")
        rig.host.start_pump()
        with pytest.raises(LiveError):
            await rig.mc.connect()
        assert rig.mc.state == "offline" and rig.mc.sessions_opened == 0 and "429" in rig.mc.reason
        await asyncio.sleep(0.3)
        assert rig.mc.state == "offline" and rig.transports == []  # no automatic retry
        assert not rig.eng.mc_enabled
        rig.port.ok = False
        rig.fail_connect = None
        with pytest.raises(LiveError, match="browser audio"):
            await rig.mc.connect()
        await rig.down()
    run(main())


def test_provider_close_goes_offline_show_continues_with_the_phone_text_box_and_no_reconnect():
    async def main():
        rig = await Rig().up()
        await buzz_to_answering(rig)
        rig.t.push(Closed("ConnectionClosedError"))
        await rig.until(lambda: rig.mc.state == "offline", timeout=3)
        assert rig.eng.round.text_box and not rig.eng.mc_enabled and not rig.eng.voice_input
        assert rig.host.run(rig.eng.phone_action, 1, {"type": "text_answer", "text": "Mirror"}).ok
        await rig.until(lambda: any(m["type"] == "buzzer.judged" for m in rig.eng.stream), timeout=10)
        await asyncio.sleep(0.3)
        assert len(rig.transports) == 1 and rig.mc.sessions_opened == 1  # nobody reconnected on their own
        # the operator reconnects explicitly: a fresh session, counted
        await rig.mc.connect()
        assert rig.mc.sessions_opened == 2 and len(rig.transports) == 2 and rig.eng.mc_enabled
        await rig.down()
    run(main())


def test_caps_stall_inactivity_and_session_length(monkeypatch):
    async def once(attr, value, setup=None):
        rig = Rig()
        await rig.up()
        if setup:
            setup(rig)
        orig = getattr(livemod, attr)
        monkeypatch.setattr(livemod, attr, value)
        try:
            await rig.until(lambda: rig.mc.state == "offline", timeout=5, ack=False)
            reason = rig.mc.reason
        finally:
            monkeypatch.setattr(livemod, attr, orig)
        await rig.down()
        return reason

    async def main():
        assert "40 min" in await once("SESSION_CAP_S", 0.2)
        assert "240 s" in await once("INACTIVE_CAP_S", 0.2)

        def stall(rig):
            rig.hold_next = True
            rig.t.hold = True
            rig.host.join("Mina"); rig.host.start(); rig.host.run(rig.eng.stage_message, "c1", {"type": "x", "data": {}})
        # a line whose generation never completes: after STALL_S the session is stopped safely
        monkeypatch.setattr(livemod, "STALL_S", 0.4)
        r = await once("INACTIVE_CAP_S", 999, setup=lambda rig: (stall(rig), rig.autoack()))
        assert "did not respond" in r or "stalled" in r
    run(main())


def test_playback_that_never_reports_stops_the_mc_safely_and_fails_the_pending_line(monkeypatch):
    monkeypatch.setattr(livemod, "STALL_S", 0.5)
    async def main():
        rig = Rig()
        await rig.up()
        rig.port.play_ms = 10_000_000  # the browser never says "played"
        rig.host.join("Mina"); rig.host.start()
        await rig.until(lambda: rig.mc.state == "offline", timeout=6)
        assert "playback stalled" in rig.mc.reason
        assert rig.eng._live == set()  # the pending line was failed so the show is not stuck
        await rig.until(lambda: rig.eng.phase not in ("opening",), timeout=5)
        await rig.down()
    run(main())


def test_goaway_resumes_with_the_handle_at_most_four_times_then_stops():
    async def main():
        rig = await Rig().up()
        for i in range(4):
            rig.t.push(ResumeHandle(f"h{i}"))
            rig.t.push(GoAway(30))
            await rig.until(lambda: len(rig.transports) == i + 2, timeout=3, ack=False)
            assert rig.mc.state == "online" and rig.t.resume == f"h{i}" and rig.mc.sessions_opened == i + 2
        rig.t.push(ResumeHandle("h-last"))
        rig.t.push(GoAway(30))
        await rig.until(lambda: rig.mc.state == "offline", timeout=3, ack=False)
        assert "resumption" in rig.mc.reason and len(rig.transports) == 5
        await rig.down()
    run(main())


def test_without_a_resume_handle_goaway_stops():
    async def main():
        rig = await Rig().up()
        rig.t.push(GoAway(10))
        await rig.until(lambda: rig.mc.state == "offline", timeout=3, ack=False)
        await rig.down()
    run(main())


def test_new_game_forgets_queued_lines_and_mic():
    async def main():
        rig = await Rig().up()
        rig.mc.queue.append(livemod._Say("t-1", "greeting", {"names": ["A"], "mode": "solo"}))
        rig.host.reset(force=True)
        assert not rig.mc.queue and rig.mc.current is None and rig.port.mic_log[-1] is False
        await rig.down()
    run(main())


# ---------------------------------------------------------------- the real transport, with the SDK stubbed (no network)
class _Dummy:
    pass


def test_gemini_transport_reads_the_key_only_at_connect_never_stores_or_logs_it(tmp_path, caplog, monkeypatch):
    env = tmp_path / "live.env"
    env.write_text("GEMINI_API_KEY=SENTINEL-KEY-12345\nOTHER=1\n")
    caplog.set_level(logging.DEBUG)
    seen = {}

    class FakeSession:
        async def receive(self):
            await asyncio.sleep(3600)
            yield

    class FakeCM:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, *a):
            return None

    class FakeClient:
        def __init__(self, api_key=None, **kw):
            seen["key"] = api_key
            self.aio = type("A", (), {"live": type("L", (), {"connect": staticmethod(lambda model, config: (seen.update(model=model, cfg=config), FakeCM())[1])})()})()

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", FakeClient)
    log = tmp_path / "sessions.log"

    async def main():
        tr = GeminiTransport(env, "gemini-3.8-live", "Despina", log, "smoke")
        assert not any("SENTINEL" in repr(v) for v in vars(tr).values())  # nothing read at construction
        await tr.connect("SYSTEM PROMPT", "resume-1")
        assert seen["key"] == "SENTINEL-KEY-12345" and seen["model"] == "gemini-3.8-live"
        assert "SENTINEL" not in repr(vars(tr))  # not kept
        cfg = seen["cfg"]
        assert cfg.session_resumption.handle == "resume-1" and cfg.output_audio_transcription is not None
        assert cfg.input_audio_transcription is None  # player speech is never transcribed
        assert cfg.realtime_input_config.automatic_activity_detection.disabled is True
        assert [d.name for d in cfg.tools[0].function_declarations] == ["report_answer", "report_reason", "report_decision"]
        await tr.close()
    run(main())
    assert "SENTINEL" not in caplog.text and "SENTINEL" not in log.read_text()
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 1 and lines[0].endswith(" smoke")  # time and purpose only


def test_missing_key_and_provider_errors_are_sanitized(tmp_path, monkeypatch):
    env = tmp_path / "live.env"
    env.write_text("OTHER=1\n")

    async def main():
        with pytest.raises(LiveError, match="not set"):
            await GeminiTransport(env, "m", "v").connect("p", None)
        env.write_text("GEMINI_API_KEY=SENTINEL-KEY-999\n")
        import google.genai as genai

        class Boom(Exception):
            code = 429

        class Client:
            def __init__(self, api_key=None, **kw):
                self.aio = type("A", (), {"live": type("L", (), {"connect": staticmethod(lambda **kw: (_ for _ in ()).throw(Boom("url?key=SENTINEL-KEY-999 quota exceeded")))})()})()
        monkeypatch.setattr(genai, "Client", Client)
        with pytest.raises(LiveError) as e:
            await GeminiTransport(env, "m", "v").connect("p", None)
        assert "SENTINEL" not in str(e.value) and "quota" not in str(e.value) and "Boom (429)" in str(e.value)
    run(main())


def test_sdk_messages_map_to_events():
    from types import SimpleNamespace as NS
    tr = GeminiTransport.__new__(GeminiTransport)
    from khqs.mc.transport import QueueTransport
    QueueTransport.__init__(tr)
    part = NS(inline_data=NS(data=b"\x01\x02"))
    tr._map(NS(server_content=NS(model_turn=NS(parts=[part]), output_transcription=NS(text="Hi"), interrupted=True, turn_complete=True),
               tool_call=NS(function_calls=[NS(id="c", name="report_answer", args={"heard": "x", "recognition": "clear"})]),
               go_away=NS(time_left="5s"), session_resumption_update=NS(new_handle="H", resumable=True)))
    got = []
    while not tr._q.empty():
        got.append(tr._q.get_nowait())
    names = [type(g).__name__ for g in got]
    assert names == ["AudioOut", "OutText", "Interrupted", "TurnComplete", "ToolCall", "GoAway", "ResumeHandle"]
    assert got[0].pcm == b"\x01\x02" and got[4].args["heard"] == "x" and got[6].handle == "H"


def test_a_buzz_that_cuts_a_reading_in_flight_still_opens_the_mic_after_the_provider_acknowledges():
    """Found by the first real run: the listen arrived while the interrupted turn was draining and nothing re-opened it."""
    async def main():
        rig = await Rig().up()
        rig.t.hold_cue = "read_buzzer"  # the reading is still being generated when the player buzzes
        rig.host.join("Mina"); rig.host.start()
        for _ in range(3):
            await rig.until(lambda: rig.eng.phase == "ox.answering")
            rig.host.run(rig.eng.phone_action, 1, {"type": "ox", "choice": "O"})
            await rig.until(lambda: rig.eng.phase != "ox.answering")
        await rig.until(lambda: rig.mc.current is not None and rig.mc.current.cue == "read_buzzer")
        assert rig.host.run(rig.eng.phone_action, 1, {"type": "buzz"}).ok
        assert rig.mc.draining and rig.mc.listen is not None and not rig.mc.listen.mic_open  # the provider has not answered yet
        from khqs.mc.transport import Interrupted, TurnComplete
        rig.t.push(Interrupted()); rig.t.push(TurnComplete())
        await rig.until(lambda: rig.mc.listen is not None and rig.mc.listen.mic_open, timeout=5)
        assert rig.port.mic_log[-1] is True
        await rig.down()
    run(main())
