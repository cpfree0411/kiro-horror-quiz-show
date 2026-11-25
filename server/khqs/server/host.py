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
            pass

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
        self._n_conn = 0
        self._poke = asyncio.Event()
        self._pump_task: asyncio.Task | None = None
        self.mc_port = BrowserPort()
        if settings.mc == "live":
            self.mc = LiveMc(self, lambda: GeminiTransport(settings.env_file, settings.live_model, settings.live_voice, settings.live_log, "play"),
                             self.mc_port)
        else:
            self.mc = MockMc(self, settings.mock_speed)
        self.recorder = Recorder(self) if settings.record else None
        self.engine = self._new_engine()
        self.flush()

    # ------------------------------------------------------------------ engine lifecycle
    def _new_engine(self) -> Engine:
        s = self.settings
        seed = secrets.randbits(63) if s.seed is None else s.seed + self.game_index
        cfg = EngineConfig(buzzer_answer_ms=s.buzzer_answer_ms)
        # the mock MC speaks (tokens, durations, captions) but cannot hear: phone text box at once
        flags = self.mc.engine_flags() if self.settings.mc == "live" else {"mc_enabled": True, "voice_input": False}
        return Engine(self.bank, self.clock, random.Random(seed), cfg, game_index=self.game_index, **flags)

    def start_pump(self) -> None:
        self._pump_task = asyncio.get_running_loop().create_task(self._pump())

    async def stop(self) -> None:
        if isinstance(self.mc, LiveMc):
            await self.mc.safe_stop("server stopping")
        self.mc.cancel_all()
        if self._pump_task:
            self._pump_task.cancel()
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
            self.run(self.engine.phone_connection, seat, False)

    # ------------------------------------------------------------------ show operations
    def join(self, name: str) -> Result:
        r = self.run(self.engine.join, name)
        if r.ok:  # the phone has until the grace period to open its socket (ticket -> controller redirect)
            asyncio.get_running_loop().call_later(self.settings.join_grace_s, self._grace_check, self.engine, r.data["seat"])
        return r

    def _grace_check(self, engine, seat: int) -> None:
        if engine is self.engine and self.phone_count(seat) == 0:
            self.run(engine.phone_connection, seat, False)

    def start(self) -> Result:
        return self.run(self.engine.start)

    def reset(self, force: bool = False) -> Result:
        if not force and self.engine.phase != "ended":
            return Result(False, "SHOW IS STILL RUNNING")
        self.mc.cancel_all()
        roles = self.engine.stage_roles()
        for seat, socks in list(self.phones.items()):
            for c in socks:
                c.send({"type": "gone"})
                c.close(4002)
        self.phones.clear()
        self.game_index += 1
        self.engine = self._new_engine()
        for conn, role in roles.items():  # primary first: every open stage socket gets the new lobby
            if conn in self.stage:
                self.stage[conn].role = self.engine.stage_hello(conn, role, None)
        self.flush()
        self.poke()
        log.info("new game index=%d", self.game_index)
        return Result(True)
