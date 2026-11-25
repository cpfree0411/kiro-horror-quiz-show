"""Simulation harness: an engine, a fake clock, a fake primary stage and a fake MC.

Every stage message and a snapshot after every step are validated with
interface/tools/validate.py::check_engine_message. Nothing here touches a network.
"""
from __future__ import annotations

import heapq
import json
import itertools
import random
import sys
from pathlib import Path

from khqs.clock import FakeClock
from khqs.engine.config import EngineConfig
from khqs.engine.core import Engine
from khqs.engine.effects import (McInterrupt, McListen, McMic, McSay, McStopListen, PhoneChanged, StageBroadcast,
                                 StageDirect)

REPO = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "interface" / "tools"))
import validate  # noqa: E402  (frozen validator, imported read-only)

sys.path.pop(0)


class SimTimeout(AssertionError):
    pass


class Sim:
    def __init__(self, content, *, seed=1, mc=True, cfg=None, game_index=0, stage=True, ack_ms=300, say_ms=800,
                 check=True, cancel_on_interrupt=True, **engine_kw):
        self.clock = FakeClock()
        self._tok = itertools.count(1)
        self.eng = Engine(content, self.clock, random.Random(seed), cfg or EngineConfig(),
                          token_factory=lambda: f"cred-{next(self._tok):04d}", game_index=game_index, mc_enabled=mc, **engine_kw)
        self.check = check
        self.ack_ms, self.say_ms = ack_ms, say_ms
        self.cancel_on_interrupt = cancel_on_interrupt
        self.conn = "stage-1"
        self.stream: list[dict] = []
        self.stream_t: list[int] = []  # clock ms when each stream message was emitted
        self.directs: list[tuple[str, dict]] = []
        self.mc_fx: list[tuple[int, object, int]] = []  # (sseq at the time, effect, clock ms)
        self.mic_fx: list[McMic] = []
        self.phone_pushes = 0
        self.snapshots: list[dict] = []
        self.views: list[tuple[int, dict]] = []  # (sseq, {seat: view})
        self.timers: list[tuple[int, int, object]] = []
        self._n = itertools.count()
        self.hooks: list = []
        self._in_hooks = False
        self.auto_ack = True
        self.auto_media = True
        self.pending_says: dict[str, list] = {}
        self.ack_filter = None  # callable(msg) -> bool; False = the stage never acks this gate
        self._media_timer = None
        self.creds: dict[int, str] = {}
        self.listens: list[McListen] = []
        self._last_snap_key = None
        self._last_views = None
        self.pump()
        if stage:
            self.hello()

    # ---------------------------------------------------------------- time
    def after(self, ms: int, fn):
        item = [self.clock.now_ms() + ms, next(self._n), fn, False]
        heapq.heappush(self.timers, item)
        return item

    def cancel(self, item):
        if item:
            item[3] = True

    def _next_time(self):
        c = []
        while self.timers and self.timers[0][3]:
            heapq.heappop(self.timers)
        if self.timers:
            c.append(self.timers[0][0])
        d = self.eng.next_due()
        if d is not None:
            c.append(d)
        return min(c) if c else None

    def run_until(self, pred, timeout_ms=900_000, what="condition"):
        end = self.clock.now_ms() + timeout_ms
        self.pump()
        while not pred():
            t = self._next_time()
            if t is None or t > end:
                raise SimTimeout(f"timed out waiting for {what}; phase={self.eng.phase} sseq={self.eng._sseq}")
            self.clock._now = max(self.clock.now_ms(), t)
            while self.timers and self.timers[0][0] <= self.clock.now_ms():
                item = heapq.heappop(self.timers)
                if not item[3]:
                    item[2]()
                    self.pump()
            self.eng.poll()
            self.pump()

    def run(self, ms: int):
        end = self.clock.now_ms() + ms
        try:
            self.run_until(lambda: self.clock.now_ms() >= end, timeout_ms=ms + 1)
        except SimTimeout:
            pass
        self.clock._now = max(self.clock.now_ms(), end)
        self.eng.poll()
        self.pump()

    def until_phase(self, phase, **kw):
        self.run_until(lambda: self.eng.phase == phase, what=f"phase {phase}", **kw)

    def until_type(self, type_, n=1, **kw):
        self.run_until(lambda: sum(m["type"] == type_ for m in self.stream) >= n, what=f"{n}x {type_}", **kw)

    def until_ended(self, **kw):
        self.until_phase("ended", **kw)

    # ---------------------------------------------------------------- effects
    def pump(self):
        while True:
            effs = self.eng.take_effects()
            if not effs:
                break
            for e in effs:
                self._handle(e)
        self._observe()
        if not self._in_hooks:
            self._in_hooks = True
            try:
                for h in list(self.hooks):
                    h(self)
            finally:
                self._in_hooks = False
            if self.eng._out:
                self.pump()

    def _validate(self, msg):
        if self.check:
            problems = validate.check_engine_message(msg)
            assert not problems, f"schema problems for {msg.get('type')} #{msg.get('sseq')}: {problems}"

    def _handle(self, e):
        if isinstance(e, StageBroadcast):
            m = e.msg
            self._validate(m)
            self.stream.append(m)
            self.stream_t.append(self.clock.now_ms())
            self._stage_reacts(m)
        elif isinstance(e, StageDirect):
            self._validate(e.msg)
            self.directs.append((e.conn, e.msg))
        elif isinstance(e, PhoneChanged):
            self.phone_pushes += 1
        elif isinstance(e, McSay):
            self.mc_fx.append((self.eng._sseq, e, self.clock.now_ms()))
            tok = e.token
            ms = self.say_ms.get(e.cue, self.say_ms.get('*', 800)) if isinstance(self.say_ms, dict) else self.say_ms
            item = self.after(ms, lambda tok=tok: self.eng.mc_played(tok))
            self.pending_says.setdefault(tok, []).append(item)
        elif isinstance(e, McListen):
            self.mc_fx.append((self.eng._sseq, e, self.clock.now_ms()))
            self.listens.append(e)
        elif isinstance(e, McStopListen):
            self.mc_fx.append((self.eng._sseq, e, self.clock.now_ms()))
        elif isinstance(e, McInterrupt):
            self.mc_fx.append((self.eng._sseq, e, self.clock.now_ms()))
            if self.cancel_on_interrupt:
                for items in self.pending_says.values():
                    for it in items:
                        self.cancel(it)
        elif isinstance(e, McMic):
            self.mic_fx.append(e)
            self.mc_fx.append((self.eng._sseq, e, self.clock.now_ms()))

    def _observe(self):
        """A snapshot and every seat's phone view after each batch of effects (stored when they changed)."""
        snap = self.eng.snapshot()
        key = (snap["sseq"], json.dumps(snap["data"], sort_keys=True))
        if key != self._last_snap_key:
            self._last_snap_key = key
            self._validate(snap)
            self.snapshots.append(snap)
        views = {s: self.eng.phone_view(s) for s in self.eng.players}
        if views != self._last_views:
            self._last_views = views
            self.views.append((self.eng._sseq, views))

    def _stage_reacts(self, m):
        t, d = m["type"], m["data"]
        if "gate" in m and self.auto_ack and (self.ack_filter is None or self.ack_filter(m)):
            gid, sseq = m["gate"]["id"], m["sseq"]
            self.after(self.ack_ms, lambda: self.stage_send("stage.beat_done", {"gate": gid, "sseq": sseq}))
        if t == "act.started" and d["assets"]:
            ids = [a["assetId"] for a in d["assets"]]
            self.after(50, lambda: self.stage_send("stage.media_ready", {"assetIds": ids}))
        if t == "av.play" and self.auto_media:
            length = int(round((d["endSec"] - d["startSec"]) * 1000))
            self._media_timer = self.after(length, lambda d=d: self.stage_send("stage.media_ended", {
                "assetId": d["assetId"], "level": d["level"], "reason": "ended", "positionSec": d["endSec"]}))
            self._last_play = d
        if t == "buzzer.pressed" and d["mediaInterrupted"] and self.auto_media:
            self.cancel(self._media_timer)
            p = self._last_play
            self.after(100, lambda: self.stage_send("stage.media_ended", {
                "assetId": p["assetId"], "level": p["level"], "reason": "interrupted", "positionSec": p["startSec"] + 1.0}))

    # ---------------------------------------------------------------- inputs
    def hello(self, conn=None, role="primary", last=None):
        r = self.eng.stage_hello(conn or self.conn, role, last)
        self.pump()
        return r

    def stage_send(self, type_, data, conn=None):
        self.eng.stage_message(conn or self.conn, {"proto": "khqs.stage/1", "type": type_, "data": data})
        self.pump()

    def join(self, name):
        r = self.eng.join(name)
        if r.ok:
            self.creds[r.data["seat"]] = r.data["credential"]
        self.pump()
        return r

    def start(self):
        r = self.eng.start()
        self.pump()
        return r

    def act(self, seat, action):
        r = self.eng.phone_action(seat, action)
        self.pump()
        return r

    # ---------------------------------------------------------------- queries
    def types(self, *, skip=("mc.status",)):
        return [m["type"] for m in self.stream if m["type"] not in skip]

    def of(self, type_):
        return [m for m in self.stream if m["type"] == type_]

    def last_listen(self, purpose=None):
        ls = [l for l in self.listens if purpose is None or l.purpose == purpose]
        return ls[-1] if ls else None


def new_sim(content, names=("Mina", "Junho", "Ray"), start=True, **kw):
    """Join so that names[i] sits on seat i (2 or 3 players). One player takes the middle seat (seat 1)."""
    sim = Sim(content, **kw)
    order = {1: [0], 2: [1, 0], 3: [1, 0, 2]}[len(names)]  # join order 1 -> 0 -> 2 puts names[i] on seat i
    for i in order:
        assert sim.join(names[i]).ok
    if start:
        assert sim.start().ok
    return sim
