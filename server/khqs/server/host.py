"""GameHost: owns the engine, the sockets and the clock pump. Everything runs on one event loop."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import secrets
from dataclasses import dataclass, field

from ..clock import Clock, SystemClock
from ..content.model import ContentBank
from ..engine.config import EngineConfig
from ..engine.core import Engine, Result
from ..engine.effects import (McInterrupt, McListen, McMic, McSay, McStopListen, PhoneChanged, StageBroadcast,
                              StageDirect)
from ..mc.live import BrowserPort, LiveMc
from ..mc.mock import MockMc
from ..mc.transport import GeminiTransport
from .record import Recorder
from .settings import Settings

log = logging.getLogger("khqs.server")
QUEUE_MAX = 200


class Conn:
    """A WebSocket with its own send queue so one slow socket never blocks the loop."""

    def __init__(self, ws, kind: str) -> None:
        self.ws, self.kind = ws, kind
        self.closed = False
        self.q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self.task = asyncio.get_running_loop().create_task(self._writer())
        self.klass = "local"  # local | public | lan
        self.ip = ""
        # stage
        self.conn_id = ""
        self.role = "viewer"
        self.cid = ""
        # phone
        self.seat: int | None = None

    def send(self, obj: dict) -> None:
        if self.closed:
            return
        try:
            self.q.put_nowait(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        except asyncio.QueueFull:
            self.close(1013)

    async def _writer(self) -> None:
        while True:
            item = await self.q.get()
            if item is None:
                break
            try:
                await self.ws.send_text(item)
            except Exception:
                self.closed = True
                break

    def close(self, code: int = 1000) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.q.put_nowait(None)
        except asyncio.QueueFull:
            self.task.cancel()  # a full queue could not take the stop marker: do not leave the writer task behind

        async def _c():
            try:
                await self.ws.close(code)
            except Exception:
                pass
        asyncio.get_running_loop().create_task(_c())


class GameHost:
    def __init__(self, settings: Settings, bank: ContentBank, clock: Clock | None = None) -> None:
        self.settings, self.bank = settings, bank
        self.clock = clock or SystemClock()
        self.game_index = 0
        self.stage: dict[str, Conn] = {}
        self.phones: dict[int, list[Conn]] = {}
        self._grace: dict[int, asyncio.TimerHandle] = {}  # seat -> pending 'no phone socket yet' check; each holds its engine alive
        self._gone: dict[int, asyncio.TimerHandle] = {}  # seat -> pending 'disconnected' (cancelled if the phone comes back)
        self._n_conn = 0
        self._poke = asyncio.Event()
        self._pump_task: asyncio.Task | None = None
        self.mc_port = BrowserPort()
        self.mock_mc = MockMc(self, settings.mock_speed)
        self.live_mc = (LiveMc(self, lambda: GeminiTransport(settings.env_file, settings.live_model, settings.live_voice, settings.live_log, "play"),
                               self.mc_port) if settings.mc == "live" else None)
        self.last_input = self.clock.now_ms()
        self.game_started_at = self.last_input
        self._caps_task: asyncio.Task | None = None
        self.caps_interval = 1.0
        self.stats_providers: list = []  # callables returning dicts (guard table sizes), for process_stats
        self.recorder = Recorder(self) if settings.record else None
        self.engine = self._new_engine()
        self.flush()

    # ------------------------------------------------------------------ engine lifecycle
    def _new_engine(self) -> Engine:
        s = self.settings
        seed = secrets.randbits(63) if s.seed is None else s.seed + self.game_index
        cfg = EngineConfig(buzzer_answer_ms=s.buzzer_answer_ms)
        # the mock MC speaks (tokens, durations, captions) but cannot hear: phone text box at once
        flags = self.mc.engine_flags()
        return Engine(self.bank, self.clock, random.Random(seed), cfg, game_index=self.game_index, **flags)

    @property
    def mc(self):
        """The MC in charge. Public mode keeps the mock for everyone unless the live MC is connected (a private show)."""
        if self.live_mc is not None and (not self.settings.public or self.live_mc.state in ("online", "connecting")):
            return self.live_mc
        return self.mock_mc

    @property
    def private_show(self) -> bool:
        return bool(self.settings.public and self.live_mc is not None and self.live_mc.state in ("online", "connecting"))

    def live_stopped(self) -> None:
        if self.settings.public:  # back to the public experience: the mock MC
            self.engine.mc_mock()

    def touch_input(self) -> None:
        self.last_input = self.clock.now_ms()

    def primary_cid(self) -> str | None:
        c = self.stage.get(self.engine.primary) if self.engine.primary else None
        return c.cid if c else None

    def has_public_clients(self) -> bool:
        return any(c.klass == "public" for c in [*self.stage.values(), *[x for cs in self.phones.values() for x in cs]])

    def start_pump(self) -> None:
        self._pump_task = asyncio.get_running_loop().create_task(self._pump())
        if self.settings.public:
            self._caps_task = asyncio.get_running_loop().create_task(self._caps())

    async def _caps(self) -> None:
        """GAME_RULES section 11 for public games: 40 minutes per game, 240 s without player input."""
        s = self.settings
        while True:
            await asyncio.sleep(self.caps_interval)
            now = self.clock.now_ms()
            e = self.engine
            if not e.players and e.phase == "lobby":
                continue
            if now - self.game_started_at >= s.game_cap_s * 1000:
                log.warning("game cap reached phase=%s players=%d", e.phase, len(e.players))
                self.reset(force=True)
            elif e.players and now - self.last_input >= s.idle_reset_s * 1000:
                log.warning("idle reset phase=%s players=%d", e.phase, len(e.players))
                self.reset(force=True)

    async def stop(self) -> None:
        if self.live_mc is not None:
            await self.live_mc.safe_stop("server stopping")
        self.mock_mc.cancel_all()
        if self.live_mc is not None:
            self.live_mc.cancel_all()
        self._cancel_timers()
        for t in (self._pump_task, self._caps_task):
            if t:
                t.cancel()
        for c in [*self.stage.values(), *[c for cs in self.phones.values() for c in cs]]:
            c.close(1001)

    async def _pump(self) -> None:
        """Sleep until the engine's next deadline; any input wakes it early. Needs no stage connected."""
        while True:
            due = self.engine.next_due()
            timeout = None if due is None else max(0.001, (due - self.clock.now_ms()) / 1000)
            try:
                await asyncio.wait_for(self._poke.wait(), timeout)
            except asyncio.TimeoutError:
                pass
            self._poke.clear()
            self.engine.poll()
            self.flush()

    def poke(self) -> None:
        self._poke.set()

    def run(self, fn, *args):
        """The only way an input reaches the engine: call, flush effects, wake the pump."""
        out = fn(*args)
        self.flush()
        self.poke()
        return out

    # ------------------------------------------------------------------ effects
    def flush(self) -> None:
        while True:
            effs = self.engine.take_effects()
            if not effs:
                break
            for e in effs:
                self._dispatch(e)
        if self.recorder:
            self.recorder.observe()

    def _dispatch(self, e) -> None:
        if isinstance(e, StageBroadcast):
            for c in self.stage.values():
                c.send(e.msg)
        elif isinstance(e, StageDirect):
            if self.recorder:
                self.recorder.on_direct(e.conn, e.msg)
            c = self.stage.get(e.conn)
            if c:
                c.send(e.msg)
        elif isinstance(e, PhoneChanged):
            for seat in e.seats:
                self._push_view(seat)
        elif isinstance(e, (McSay, McListen, McStopListen, McInterrupt, McMic)):
            if self.recorder:
                self.recorder.on_mc(e)
            self.mc.handle(e)

    def _push_view(self, seat: int) -> None:
        socks = self.phones.get(seat)
        if not socks:
            return
        view = self.engine.phone_view(seat)
        if view is None:
            return
        for c in socks:
            c.send({"type": "view", "view": view})

    # ------------------------------------------------------------------ stage sockets
    def new_conn_id(self) -> str:
        self._n_conn += 1
        return f"s{self._n_conn}"

    def stage_hello(self, sock: Conn, role: str, last_sseq, cid: str, take: bool) -> str:
        eng = self.engine
        if role == "primary" and eng.primary is not None and eng.primary != sock.conn_id:
            old = self.stage.get(eng.primary)
            if old is not None and (take or (cid and old.cid == cid)):
                self.drop_stage(old, 4001)  # reconnect race / operator take-over: the newest socket wins
        sock.cid = cid
        self.stage[sock.conn_id] = sock
        sock.role = self.run(eng.stage_hello, sock.conn_id, role, last_sseq)
        return sock.role

    def drop_stage(self, sock: Conn, code: int = 1000) -> None:
        if self.stage.get(sock.conn_id) is sock:
            del self.stage[sock.conn_id]
            self.engine.stage_disconnect(sock.conn_id)
        sock.close(code)

    def stage_closed(self, sock: Conn) -> None:
        if self.stage.get(sock.conn_id) is sock:
            self.run(self.engine.stage_disconnect, sock.conn_id)
            self.stage.pop(sock.conn_id, None)

    # ------------------------------------------------------------------ phone sockets
    def phone_hello(self, sock: Conn, credential: str) -> bool:
        seat = self.engine.seat_for_credential(credential)
        if seat is None:
            return False
        socks = self.phones.setdefault(seat, [])
        sock.seat = seat
        socks.append(sock)
        pending = self._gone.pop(seat, None)
        if pending is not None:
            pending.cancel()  # back within the grace time: the stage never heard about it
        joined = self._grace.pop(seat, None)
        if joined is not None:
            joined.cancel()  # the phone showed up: nothing left to check
        if len(socks) == 1:
            self.run(self.engine.phone_connection, seat, True)
        self._push_view(seat)
        return True

    def phone_count(self, seat: int) -> int:
        return len(self.phones.get(seat, []))

    def phone_closed(self, sock: Conn) -> None:
        seat = sock.seat
        socks = self.phones.get(seat) if seat is not None else None
        if socks is None or sock not in socks:
            return
        socks.remove(sock)
        if not socks:
            del self.phones[seat]
            engine = self.engine
            self._gone[seat] = asyncio.get_running_loop().call_later(self.settings.disconnect_grace_s, self._announce_gone, engine, seat)

    def _announce_gone(self, engine, seat: int) -> None:
        self._gone.pop(seat, None)
        if engine is self.engine and self.phone_count(seat) == 0:
            self.run(engine.phone_connection, seat, False)

    # ------------------------------------------------------------------ show operations
    def join(self, name: str) -> Result:
        self.touch_input()
        r = self.run(self.engine.join, name)
        if r.ok:  # the phone has until the grace period to open its socket (ticket -> controller redirect)
            seat = r.data["seat"]
            self._grace[seat] = asyncio.get_running_loop().call_later(self.settings.join_grace_s, self._grace_check, self.engine, seat)
        return r

    def _grace_check(self, engine, seat: int) -> None:
        self._grace.pop(seat, None)
        if engine is self.engine and self.phone_count(seat) == 0:
            self.run(engine.phone_connection, seat, False)

    def _cancel_timers(self) -> None:
        for table in (self._grace, self._gone):
            for h in table.values():
                h.cancel()
            table.clear()

    def start(self) -> Result:
        self.touch_input()
        return self.run(self.engine.start)

    def reset(self, force: bool = False) -> Result:
        if not force and self.engine.phase != "ended":
            return Result(False, "SHOW IS STILL RUNNING")
        self.mock_mc.cancel_all()
        if self.live_mc is not None:
            self.live_mc.cancel_all()
        self.touch_input()
        roles = self.engine.stage_roles()
        for seat, socks in list(self.phones.items()):
            for c in socks:
                c.send({"type": "gone"})
                c.close(4002)
        self.phones.clear()
        self._cancel_timers()  # they would keep the finished game's engine (and its whole stream) alive
        self.game_index += 1
        self.engine = self._new_engine()
        self.game_started_at = self.clock.now_ms()
        for conn, role in roles.items():  # primary first: every open stage socket gets the new lobby
            if conn in self.stage:
                self.stage[conn].role = self.engine.stage_hello(conn, role, None)
        self.flush()
        self.poke()
        log.info("new game index=%d", self.game_index)
        return Result(True)
