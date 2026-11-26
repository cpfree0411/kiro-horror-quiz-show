"""A rig for LiveMc tests: a fake Live transport, a fake browser audio port, a host with tiny windows. No network."""
import array
import asyncio
import math
import random

from khqs.content.dev_bank import build_dev_bank
from khqs.engine.config import EngineConfig
from khqs.engine.core import Engine
from khqs.engine.effects import McSay
from khqs.mc.live import LiveMc
from khqs.mc.transport import AudioOut, Closed, Interrupted, OutText, QueueTransport, ToolCall, TurnComplete
from khqs.server.host import GameHost
from settings_util import make_settings


def tone(ms, amp, rate=16000):
    n = int(rate * ms / 1000)
    return array.array("h", [int(amp * math.sin(i / 3)) for i in range(n)]).tobytes()


class FakeTransport(QueueTransport):
    """Scripted Live session. `reply(text)` returns (spoken_text, ms_of_audio) for a turn; None = silent turn."""

    def __init__(self, log, fail_connect=None):
        super().__init__()
        self.log, self.fail_connect = log, fail_connect
        self.turns, self.contexts, self.audio, self.activities, self.tool_results = [], [], [], [], []
        self.positions = []
        self.sseq_now = lambda: 0
        self.hold_cue = None  # hold (never complete) only turns for this cue
        self.hold = False  # when True, turns produce audio but never complete (a long reading)
        self.tool_script = None  # callable(listen purpose) -> list[ToolCall], consulted on activity end
        # How the real Live API behaves around a tool call (seen in the owner's play test): the model's turn that made the
        # call stays open until the tool response arrives, then it completes (empty) a few ms later. A client turn sent
        # before that is answered only after it. `tool_turn_ms=None` models an API that sends no such completion.
        self.tool_turn_ms: float | None = 30
        self._tool_open = False
        self._deferred: list[str] = []
        self.empty_cues: dict[str, int] = {}  # cue -> how many turns for it come back as a bare turn_complete

    async def connect(self, system_prompt, resume):
        if self.fail_connect:
            raise self.fail_connect
        self.system_prompt, self.resume = system_prompt, resume
        self.log.append(self)

    async def send_turn(self, text):
        self.turns.append(text)
        self.positions.append(self.sseq_now())
        if self._tool_open:  # the open tool turn finishes first; this turn is answered after it
            self._deferred.append(text)
            return
        self._respond(text)

    def _finish_tool_turn(self):
        self._tool_open = False
        self.push(TurnComplete())  # the (empty) rest of the turn that made the tool call
        for text in self._deferred:
            self._respond(text)
        self._deferred.clear()

    def _respond(self, text):
        cue = text.split("]", 1)[0].removeprefix("[CUE ") if text.startswith("[CUE ") else ""
        if self.empty_cues.get(cue, 0) > 0:
            self.empty_cues[cue] -= 1
            self.push(TurnComplete())  # a turn with no audio at all
            return
        spoken = "Fine words."
        self.push(AudioOut(tone(50, 3000, 24000)))
        self.push(OutText(spoken))
        if not (self.hold or (self.hold_cue and text.startswith(f"[CUE {self.hold_cue}]"))):
            self.push(AudioOut(tone(50, 3000, 24000)))
            self.push(TurnComplete())

    async def send_context(self, text):
        self.contexts.append(text)

    async def send_audio(self, pcm):
        self.audio.append(pcm)

    async def activity(self, start):
        self.activities.append(start)
        if not start and self.tool_script:
            for c in self.tool_script():
                self.push(c)

    async def tool_result(self, call_id, name):
        self.tool_results.append((call_id, name, {"received": True}))
        if self.tool_turn_ms is not None:
            self._tool_open = True
            asyncio.get_running_loop().call_later(self.tool_turn_ms / 1000, self._finish_tool_turn)

    async def close(self):
        self.closed = True
        self.push(Closed("closed by us"))


class FakePort:
    """The browser's audio socket: records what it was told and plays lines back in (scaled) real time."""

    def __init__(self, mc_getter, play_ms=60):
        self.mc_getter, self.play_ms = mc_getter, play_ms
        self.ok = True
        self.audio_log, self.ended, self.flushes, self.mic_log = [], [], 0, []
        self._timers = {}

    def available(self):
        return self.ok

    def audio(self, token, pcm):
        self.audio_log.append((token, len(pcm)))

    def end(self, token):
        self.ended.append(token)
        loop = asyncio.get_running_loop()
        mc = self.mc_getter()
        h1 = loop.call_later(self.play_ms / 2000, mc.on_started, token)
        h2 = loop.call_later(self.play_ms / 1000, mc.on_played, token)
        self._timers[token] = (h1, h2)

    def flush(self):
        self.flushes += 1
        for h in [x for pair in self._timers.values() for x in pair]:
            h.cancel()
        self._timers.clear()

    def mic(self, open_):
        self.mic_log.append(open_)


class RigHost(GameHost):
    def _new_engine(self):
        cfg = EngineConfig(ox_answer_ms=400, betrayal_input_ms=300, prompt_failsafe_ms=3000, reading_failsafe_ms=3000,
                           buzzer_answer_ms=4000, buzzer_open_ms=1500, music_open_ms=300, media_interrupt_wait_ms=100,
                           media_watchdog_extra_ms=100, hint_consent_ms=2500, final_bet_ms=300, final_answer_ms=300, gate_grace_ms=500,
                           gate_timeouts={k: 60 for k in EngineConfig().gate_timeouts})
        flags = self.mc.engine_flags()
        return Engine(self.bank, self.clock, random.Random(3), cfg, game_index=self.game_index, **flags)


class Rig:
    def __init__(self, **settings_kw):
        s = make_settings(mc="live", record=True, **settings_kw)
        self.host = RigHost(s, build_dev_bank(s.media_dir))
        self.transports = []
        self.port = FakePort(lambda: self.host.mc)
        self.host.mc.port = self.port
        self.host.mc.factory = lambda: self.new_transport()
        self.fail_connect = None
        self.hold_next = False

    def new_transport(self):
        t = FakeTransport(self.transports, self.fail_connect)
        t.sseq_now = lambda: self.eng._sseq
        t.hold = self.hold_next
        return t

    @property
    def mc(self):
        return self.host.mc

    @property
    def eng(self):
        return self.host.engine

    @property
    def t(self):
        return self.transports[-1]

    async def up(self):
        self.host.start_pump()
        await self.mc.connect()
        self.host.run(self.eng.stage_hello, "c1", "primary", None)
        self.acked = set()
        return self

    def autoack(self):
        g = self.eng.gate
        if g is not None and g.id not in self.acked:
            self.acked.add(g.id)
            self.host.run(self.eng.stage_message, "c1", {"type": "stage.beat_done", "data": {"gate": g.id, "sseq": g.sseq}})

    async def until(self, pred, timeout=20.0, ack=True):
        end = asyncio.get_running_loop().time() + timeout
        while not pred():
            if asyncio.get_running_loop().time() > end:
                raise AssertionError(f"timeout; phase={self.eng.phase} q={self.eng.question_no} mc={self.mc.state}/{self.mc.reason}")
            if ack:
                self.autoack()
            await asyncio.sleep(0.01)

    async def down(self):
        await self.host.stop()

    def turns_as_says_with_positions(self):
        return [(pos, McSay("p", "x", {"prompt": text}), 0) for pos, text in zip(self.t.positions, self.t.turns)]

    def turns_as_says(self):
        """Every text sent to the model, as fake McSay records at the stream position they were sent (for the scanner)."""
        return [(0, McSay("p", "x", {"prompt": t}), 0) for t in self.t.turns + self.t.contexts]


def run(coro):
    return asyncio.run(coro)
