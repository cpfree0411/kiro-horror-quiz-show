"""LiveMc: the engine's MC effects <-> one Live session <-> the browser's audio.

One session at a time, no automatic reconnect (only the GoAway/resumption handoff, at most 4 times). Any failure leaves
the MC offline and the show continues without voice until the operator reconnects.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..engine.effects import McInterrupt, McListen, McMic, McSay, McStopListen
from . import prompts
from .transport import (AudioOut, Closed, GoAway, Interrupted, LiveError, OutText, ResumeHandle, ToolCall, TurnComplete)
from .voice import VoiceMeter

log = logging.getLogger("khqs.mc")

SESSION_CAP_S = 40 * 60
INACTIVE_CAP_S = 240
STALL_S = 35
MAX_RESUMES = 4
NO_SPEECH_S = 7.0
TOOL_WAIT_S = 6.0
DRAIN_S, DRAIN_LATE_S = 1.5, 0.3
HEARD_MAX = 200
MAX_REARMS = 4


class AudioPort(Protocol):
    """The browser's audio socket, seen from the adapter."""
    def available(self) -> bool: ...
    def audio(self, token: str, pcm24k: bytes) -> None: ...
    def end(self, token: str) -> None: ...
    def flush(self) -> None: ...
    def mic(self, open_: bool) -> None: ...


@dataclass
class _Say:
    token: str
    cue: str
    facts: dict
    text: str = ""
    sent_at: float = 0.0
    uid: int = 0


@dataclass
class _Listen:
    id: str
    seat: int
    purpose: str
    attempt: int
    meter: VoiceMeter = field(default_factory=VoiceMeter)
    mic_open: bool = False
    opened_at: float = 0.0
    activity_open: bool = False
    speech_ended: bool = False
    task: asyncio.Task | None = None
    rearms: int = 0


class LiveMc:
    def __init__(self, host, transport_factory: Callable, port: AudioPort, *, clock=time.monotonic) -> None:
        self.host, self.factory, self.port, self.now = host, transport_factory, port, clock
        self.state = "offline"  # offline | connecting | online
        self.reason = "not connected"
        self.sessions_opened = 0
        self.resumes = 0
        self.transport = None
        self.resume_handle: str | None = None
        self.queue: deque[_Say] = deque()
        self.current: _Say | None = None
        self.awaiting: dict[str, float] = {}  # token -> time its audio was complete, until the browser says "played"
        self.listen: _Listen | None = None
        self.engine_mic_open = True
        self.draining = False
        self._drain_event: asyncio.Event | None = None
        self._utterance = 0
        self._tasks: list[asyncio.Task] = []
        self._advancing = False
        self.started_at = self.last_activity = self.last_progress = 0.0
        self.sent_turns: list[str] = []  # everything sent as text (for tests and audit; never contains the key)
        self.sent_sseq: list[int] = []  # the stream position when each turn was sent

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        return {"mode": "live", "state": self.state, "reason": self.reason, "sessionsOpened": self.sessions_opened}

    def engine_flags(self) -> dict:
        on = self.state == "online"
        return {"mc_enabled": on, "voice_input": on, "status_from_playback": True}

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self._tasks.append(t)
        t.add_done_callback(lambda x: self._tasks.remove(x) if x in self._tasks else None)
        return t

    # ------------------------------------------------------------------ connect / stop
    async def connect(self) -> None:
        if self.state != "offline":
            raise LiveError("the MC is already connected or connecting")
        if not self.port.available():
            raise LiveError("the browser audio is not connected")
        self.state, self.reason = "connecting", "connecting"
        tr = self.factory()
        try:
            await tr.connect(prompts.system_prompt(), self.resume_handle)
        except LiveError as e:
            self.state, self.reason = "offline", str(e)
            raise
        except Exception as e:  # noqa: BLE001
            self.state, self.reason = "offline", f"connect failed ({type(e).__name__})"
            raise LiveError(self.reason) from None
        self.transport = tr
        self.sessions_opened += 1
        self.state, self.reason = "online", "ok"
        self.started_at = self.last_activity = self.last_progress = self.now()
        self.resumes = 0
        self._spawn(self._reader(tr))
        self._spawn(self._watchdog())
        self.host.run(self.host.engine.mc_online, True)

    async def disconnect(self, reason: str = "closed by the operator") -> None:
        await self.safe_stop(reason)

    async def safe_stop(self, reason: str) -> None:
        if self.state == "offline":
            return
        log.warning("live MC stopped: %s", reason)
        self.state, self.reason = "offline", reason
        tr, self.transport = self.transport, None
        self.queue.clear()
        self.current = None
        self.awaiting.clear()
        self._drop_listen()
        for t in list(self._tasks):
            if t is not asyncio.current_task():
                t.cancel()
        self.port.flush()
        self.port.mic(False)
        if tr is not None:
            try:
                await tr.close()
            except Exception:  # noqa: BLE001
                pass
        self.host.run(self.host.engine.mc_offline)
        self.host.live_stopped()

    def cancel_all(self) -> None:
        """New game or forced reset: forget everything queued (tokens belong to the old engine)."""
        self.queue.clear()
        self.current = None
        self.awaiting.clear()
        self._drop_listen()
        self.port.flush()
        self.port.mic(False)

    # ------------------------------------------------------------------ engine effects
    def handle(self, e) -> None:
        if self.state != "online":
            return
        self.last_activity = self.now()
        if isinstance(e, McSay):
            self.queue.append(_Say(e.token, e.cue, e.facts))
            self._spawn(self._advance())
        elif isinstance(e, McListen):
            self._drop_listen()
            self.listen = _Listen(e.listen_id, e.seat, e.purpose, e.attempt)
            self._spawn(self._pump_listen())
        elif isinstance(e, McStopListen):
            if self.listen and self.listen.id == e.listen_id:
                self._spawn(self._stop_listen())
        elif isinstance(e, McInterrupt):
            self._interrupt()
        elif isinstance(e, McMic):
            self.engine_mic_open = e.open
            if not e.open and self.listen and self.listen.mic_open:
                self.listen.mic_open = False
                self.port.mic(False)
            else:
                self._spawn(self._pump_listen())

    # ------------------------------------------------------------------ speaking
    def _idle(self) -> bool:
        return not self.queue and self.current is None and not self.awaiting and not self.draining

    async def _advance(self) -> None:
        if self._advancing:
            return
        self._advancing = True
        try:
            while self.state == "online" and self.queue and self.current is None:
                if self.draining:
                    await self._wait_drain()
                    continue
                say = self.queue.popleft()
                self.current = say
                text = prompts.turn_for(say.cue, say.facts)
                self._utterance += 1
                say.uid = self._utterance
                say.sent_at = self.last_progress = self.now()
                self.sent_turns.append(text)
                self.sent_sseq.append(self.host.engine._sseq)
                try:
                    await self.transport.send_turn(text)
                except LiveError as e:
                    await self.safe_stop(f"send failed: {e}")
                    return
        finally:
            self._advancing = False

    def _interrupt(self) -> None:
        had = self.current is not None
        self.queue.clear()
        self.current = None
        self.awaiting.clear()
        self.port.flush()
        if had:  # the provider will report `interrupted` and maybe a late `turn_complete`; wait for them before the next turn
            self.draining = True
            self._drain_event = asyncio.Event()
            self._spawn(self._drain_timeout())

    async def _drain_timeout(self) -> None:
        await asyncio.sleep(DRAIN_S + DRAIN_LATE_S)
        self._finish_drain()

    def _finish_drain(self) -> None:
        self.draining = False
        if self._drain_event:
            self._drain_event.set()
        self._spawn(self._pump_listen())  # a listen that arrived while we were draining can open the mic now

    async def _wait_drain(self) -> None:
        if self._drain_event:
            await self._drain_event.wait()

    # ------------------------------------------------------------------ browser reports
    def on_started(self, token: str) -> None:
        self.last_progress = self.now()
        self.host.run(self.host.engine.mc_started, token)

    def on_played(self, token: str) -> None:
        self.awaiting.pop(token, None)
        self.last_progress = self.now()
        self.host.run(self.host.engine.mc_played, token)
        self._spawn(self._pump_listen())

    # ------------------------------------------------------------------ provider events
    async def _reader(self, tr) -> None:
        async for ev in tr.events():
            if tr is not self.transport:
                return
            try:
                await self._on_event(ev)
            except LiveError as e:
                await self.safe_stop(f"provider error: {e}")
                return
            if isinstance(ev, Closed):
                if self.state == "online" and tr is self.transport:
                    await self.safe_stop(f"the Live session closed ({ev.reason})")
                return

    async def _on_event(self, ev) -> None:
        if isinstance(ev, AudioOut):
            if self.current and not self.draining:
                self.last_progress = self.now()
                self.port.audio(self.current.token, ev.pcm)
        elif isinstance(ev, OutText):
            if self.current and not self.draining:
                self.current.text += ev.text
                self._caption(self.current, False)
        elif isinstance(ev, Interrupted):
            if self.draining:
                return  # expected after our interrupt; a late TurnComplete may follow and is absorbed by the drain window
            if self.current:  # the provider cut the line short on its own: finish it as it is
                await self._complete()
        elif isinstance(ev, TurnComplete):
            if self.draining:
                self._finish_drain()
                return
            await self._complete()
        elif isinstance(ev, ToolCall):
            await self._on_tool(ev)
        elif isinstance(ev, GoAway):
            self._spawn(self._resume())
        elif isinstance(ev, ResumeHandle):
            self.resume_handle = ev.handle

    async def _complete(self) -> None:
        say = self.current
        if say is None:
            return  # a late turn_complete after interrupted: normal
        self.current = None
        self.last_progress = self.now()
        self._caption(say, True)
        self.port.end(say.token)
        self.awaiting[say.token] = self.now()
        self._spawn(self._advance())

    def _caption(self, say: _Say, final: bool) -> None:
        """The model's own words, through the engine's secret filter. Player speech is never captioned."""
        if say.text.strip():
            self.host.run(self.host.engine.mc_caption, say.uid, say.text, final)

    # ------------------------------------------------------------------ listening
    def _drop_listen(self) -> None:
        l, self.listen = self.listen, None
        if l and l.task:
            l.task.cancel()
        if l and l.mic_open:
            self.port.mic(False)

    async def _pump_listen(self) -> None:
        l = self.listen
        if l is None or l.mic_open or l.speech_ended or not self.engine_mic_open or not self._idle() or self.state != "online":
            return
        l.mic_open, l.opened_at = True, self.now()
        self.port.mic(True)
        try:
            await self.transport.send_context(prompts.listen_context(l.purpose, self.host.engine.players[l.seat].name, l.attempt))
        except LiveError:
            pass  # context is a nicety; the system prompt already says what to do
        if self.listen is l:
            l.task = self._spawn(self._no_speech(l))

    async def _no_speech(self, l: _Listen) -> None:
        await asyncio.sleep(NO_SPEECH_S)
        if self.listen is l and not l.meter.started:  # nothing voiced: a recognition failure, without touching Live
            await self._fail(l)

    async def on_mic(self, pcm: bytes) -> None:
        l = self.listen
        if l is None or not l.mic_open or self.state != "online":
            return  # the gate: audio that arrives while the engine did not ask for it is dropped
        r = l.meter.feed(pcm)
        try:
            if r.started:
                l.activity_open = True
                await self.transport.activity(True)
            if r.forward and l.activity_open:
                await self.transport.send_audio(r.forward)
            if r.ended:
                await self._end_speech(l)
        except LiveError as e:
            await self.safe_stop(f"send failed: {e}")

    async def _end_speech(self, l: _Listen) -> None:
        l.speech_ended, l.mic_open = True, False
        self.port.mic(False)
        if l.activity_open:
            await self.transport.activity(False)
        l.task = self._spawn(self._tool_wait(l))

    async def _tool_wait(self, l: _Listen) -> None:
        await asyncio.sleep(TOOL_WAIT_S)
        if self.listen is l:  # speech ended and the model never called the tool: not understood
            await self._fail(l)

    async def _stop_listen(self) -> None:
        l = self.listen
        if l is None:
            return
        was_active = l.activity_open and not l.speech_ended
        self._drop_listen()
        if was_active and self.state == "online":
            try:
                await self.transport.activity(False)  # close the activity; any tool call that follows is stale and ignored
            except LiveError:
                pass

    def _rearm(self, l: _Listen) -> bool:
        """Consent only: the room may speak more than once, so the same listen stays open for the next voice until the engine ends the window."""
        if self.listen is not l or l.rearms >= MAX_REARMS:
            return False
        if l.task:
            l.task.cancel()
            l.task = None
        l.rearms += 1
        l.meter, l.mic_open, l.speech_ended, l.activity_open = VoiceMeter(), False, False, False
        self._spawn(self._pump_listen())
        return True

    async def _fail(self, l: _Listen) -> None:
        if l.purpose == "consent" and self._rearm(l):
            return  # nothing usable was heard; silence counts as yes, so the engine needs no report
        self._drop_listen()
        if l.purpose == "answer":
            self.host.run(self.host.engine.mc_voice_answer, l.id, "", "unclear", l.meter.voiced)

    async def _on_tool(self, call: ToolCall) -> None:
        l = self.listen
        try:
            await self.transport.tool_result(call.id, call.name)  # silent receipt: {"received": true} and nothing else
        except LiveError as e:
            await self.safe_stop(f"send failed: {e}")
            return
        want = {"answer": "report_answer", "reason": "report_reason", "decision": "report_decision", "consent": "report_vote"}
        if l is None or want.get(l.purpose) != call.name:
            return  # stale or unexpected: ignored
        a = call.args or {}
        heard = a.get("heard") if isinstance(a.get("heard"), str) else ""
        heard = heard.strip()[:HEARD_MAX]
        eng = self.host.engine
        if l.purpose == "consent":  # the engine classifies the words; the window stays open for the next voice
            rec = "clear" if a.get("recognition") == "clear" else "unclear"
            voiced = l.meter.voiced
            self._rearm(l)
            self.host.run(eng.mc_voice_consent, l.id, heard, rec, voiced)
            return
        self._drop_listen()
        if l.purpose == "answer":
            rec = "clear" if a.get("recognition") == "clear" else "unclear"
            eng_call = (eng.mc_voice_answer, l.id, heard, rec, l.meter.voiced)
        elif l.purpose == "reason":
            eng_call = (eng.mc_voice_reason, l.id, heard)
        else:
            d = a.get("decision")
            eng_call = (eng.mc_voice_decision, l.id, True if d == "switch" else False if d == "keep" else None)
        self.host.run(*eng_call)

    # ------------------------------------------------------------------ caps, resumption
    async def _watchdog(self) -> None:
        while self.state == "online":
            await asyncio.sleep(1.0)
            n = self.now()
            if n - self.started_at >= SESSION_CAP_S:
                return await self.safe_stop("session length cap (40 min)")
            if n - self.last_activity >= INACTIVE_CAP_S:
                return await self.safe_stop("no show activity for 240 s")
            if self.current is not None and n - self.last_progress >= STALL_S:
                return await self.safe_stop("the MC did not respond (35 s)")
            late = [t for t, at in self.awaiting.items() if n - at >= STALL_S]
            if late:
                return await self.safe_stop("browser audio playback stalled (35 s)")

    async def _resume(self) -> None:
        if self.state != "online":
            return
        if self.resumes >= MAX_RESUMES or not self.resume_handle:
            return await self.safe_stop("the provider asked us to leave and resumption is not available")
        self.resumes += 1
        old = self.transport
        new = self.factory()
        try:
            await new.connect(prompts.system_prompt(), self.resume_handle)
        except LiveError as e:
            return await self.safe_stop(f"resumption failed: {e}")
        self.transport = new
        self.sessions_opened += 1
        self._spawn(self._reader(new))
        try:
            await old.close()
        except Exception:  # noqa: BLE001
            pass


class BrowserPort:
    """AudioPort over the stage page's /ws/mc socket."""

    def __init__(self) -> None:
        self.conn = None

    def available(self) -> bool:
        return self.conn is not None and not self.conn.closed

    def _send(self, obj: dict) -> None:
        if self.available():
            self.conn.send(obj)

    def audio(self, token, pcm24k):
        self._send({"t": "a", "k": token, "d": base64.b64encode(pcm24k).decode("ascii")})

    def end(self, token):
        self._send({"t": "end", "k": token})

    def flush(self):
        self._send({"t": "flush"})

    def mic(self, open_):
        self._send({"t": "mic", "open": bool(open_)})
