"""The game engine: state, stage stream, gates, timers, inputs. No I/O.

Outside code feeds inputs (stage messages, player actions, MC events, `poll()`) and drains effects.
The show itself is a generator in `flow.py` that yields `Wait` objects.
"""
from __future__ import annotations

import logging
import random
import secrets as _secrets
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional

from ..clock import Clock
from ..content.model import ContentBank, GameContent, Question
from ..rules import scoring
from ..rules.captions import CaptionFilter, CaptionSecrets
from ..rules.judge import normalize
from . import views
from .config import EngineConfig
from .effects import (CUE_FACTS, Effect, McInterrupt, McListen, McMic, McSay, McStopListen, PhoneChanged,
                      StageBroadcast, StageDirect)
from .rounds import BETRAYAL_REASONS, BuzzRound, FinalRound, OxRound
from .waits import Gate, Wait

log = logging.getLogger("khqs.engine")

PROTO = "khqs.stage/1"
FANS = ("vampire", "sack", "bolt", "tophat_skull")  # the only four with art
NAME_MAX = 12
SEATS = (0, 1, 2)
JOIN_ORDER = (1, 0, 2)  # first joiner takes the middle seat, so a solo player is centred
HEARD_MAX = 200


@dataclass(frozen=True)
class Result:
    ok: bool
    error: str | None = None
    data: dict | None = None


@dataclass
class Player:
    seat: int
    id: str
    name: str
    fan: str
    credential: str  # private
    score: int = 0
    connected: bool = True


class Engine:
    def __init__(
        self,
        content: ContentBank | GameContent,
        clock: Clock,
        rng: random.Random,
        config: EngineConfig | None = None,
        *,
        token_factory: Callable[[], str] | None = None,
        game_index: int = 0,
        mc_enabled: bool = True,
        voice_input: bool | None = None,
        status_from_playback: bool = False,
    ) -> None:
        self.clock = clock
        self.rng = rng
        self.cfg = config or EngineConfig()
        self._token_factory = token_factory or (lambda: _secrets.token_urlsafe(16))
        self.mc_enabled = mc_enabled
        # the MC may speak but not hear (the mock MC): the holder then gets the phone text box at once
        self.voice_input = mc_enabled if voice_input is None else (voice_input and mc_enabled)
        self.stats = {"gate_timeouts": 0}
        # live MC: `speaking` follows the browser's real playback start (mc_started), not the moment a line is issued
        self.status_from_playback = status_from_playback
        self.game_index = game_index
        self.content: GameContent = content.select(game_index, rng) if isinstance(content, ContentBank) else content
        self.game_id = f"game-{game_index + 1}"
        # stream and outbox
        self.stream: list[dict] = []
        self._sseq = 0
        self._out: list[Effect] = []
        self._dirty: set[int] = set()
        # stage connections
        self._conns: dict[str, str] = {}  # conn -> effective role
        self.primary: str | None = None
        self.media_ready: set[str] = set()
        # game state
        self.players: dict[int, Player] = {}
        self._joined = 0
        self.mode = "solo"
        self.phase = "lobby"
        self.phase_started_at = self.now()
        self.deadline: int | None = None  # public deadline (as last sent in phase.changed)
        self.input_deadline: int | None = None  # private input window shown on phones
        self.act = 0
        self.q: Question | None = None
        self.q_text_visible = True
        self.hint_level = 0
        self.question_no = 0
        self.round: OxRound | BuzzRound | FinalRound | None = None
        self.ox_streak = 0
        self.gate: Gate | None = None
        self.mc_status = "idle"
        self.revealed_answer: str | None = None
        self._settled: set[str] = set()
        self._mic_open = True
        # MC
        self._live: set[str] = set()
        self._n_tokens = 0
        self._n_listens = 0
        self._captions = CaptionFilter()
        # generator
        self._gen = None
        self._wait: Wait | None = None
        self._running = False
        self.emit("phase.changed", {"phase": "lobby", "deadline": None})  # sseq 1: lets a lobby snapshot be valid

    # ------------------------------------------------------------------ basics
    def now(self) -> int:
        return self.clock.now_ms()

    def names(self) -> list[str]:
        return [self.players[s].name for s in sorted(self.players)]

    def scores(self) -> dict[int, int]:
        return {s: p.score for s, p in self.players.items()}

    def ranks(self) -> dict[int, int]:
        return scoring.rank_scores(self.scores())

    def connected_seats(self) -> list[int]:
        return [s for s in sorted(self.players) if self.players[s].connected]

    def all_connected_done(self, done: Callable[[int], bool]) -> bool:
        """True when at least one player is connected and every connected player satisfies `done`."""
        cs = self.connected_seats()
        return bool(cs) and all(done(s) for s in cs)

    def _touch(self, *seats: int) -> None:
        self._dirty.update(seats)

    def _touch_all(self) -> None:
        self._dirty.update(self.players)

    def take_effects(self) -> list[Effect]:
        out, self._out = self._out, []
        if self._dirty:
            out.append(PhoneChanged(tuple(sorted(self._dirty))))
            self._dirty = set()
        return out

    def next_due(self) -> int | None:
        return self._wait.until if self._wait is not None else None

    def poll(self) -> None:
        self._check()

    # ------------------------------------------------------------------ stream
    def emit(self, type_: str, data: dict, gate_ms: int | None = None) -> dict:
        self._sseq += 1
        msg: dict = {"proto": PROTO, "type": type_, "sseq": self._sseq, "at": self.now(), "data": data}
        if gate_ms is not None:
            msg["gate"] = {"id": f"g-{self._sseq}", "timeoutMs": gate_ms}
        self.stream.append(msg)
        self._out.append(StageBroadcast(msg))
        self._touch_all()
        return msg

    def set_phase(self, phase: str, deadline: int | None = None) -> None:
        self.phase = phase
        self.phase_started_at = self.now()
        self.deadline = deadline
        self.input_deadline = deadline
        log.info("phase=%s players=%d", phase, len(self.players))
        self.emit("phase.changed", {"phase": phase, "deadline": deadline})

    def snapshot(self) -> dict:
        return {"proto": PROTO, "type": "snapshot", "sseq": self._sseq, "at": self.now(), "data": views.snapshot_data(self)}

    def seats_wire(self) -> list[dict]:
        return views.seats_wire(self)

    # ------------------------------------------------------------------ gates
    def open_gate(self, type_: str, data: dict, *, kind: str | None = None,
                  reaction: tuple[str, dict] | None = None) -> Gate:
        if self.gate is not None:
            raise RuntimeError("one gate at a time")
        ms = self.cfg.gate_timeout(type_, kind)
        msg = self.emit(type_, data, gate_ms=ms)
        now = self.now()
        g = Gate(id=msg["gate"]["id"], sseq=msg["sseq"], type=type_, timeout_ms=ms, opened_at=now,
                 safety_at=now + ms + self.cfg.gate_grace_ms, reaction=reaction)
        self.gate = g
        return g

    def gate_wait(self, g: Gate) -> Wait:
        return Wait(until=g.safety_at, ready=lambda: self._gate_done(g))

    def _gate_done(self, g: Gate) -> bool:
        return g.acked and (g.token is None or g.token not in self._live)

    def close_gate(self, g: Gate) -> None:
        if not self._gate_done(g):
            self.stats["gate_timeouts"] += 1  # closed by the safety deadline, not by ack + reaction
        if self.gate is g:
            self.gate = None
        self._touch_all()

    def _ack_gate(self, g: Gate) -> None:
        g.acked = True
        if g.reaction is not None:
            cue, facts = g.reaction
            g.token = self.say(cue, facts)  # screen first, MC second

    # ------------------------------------------------------------------ MC output
    def say(self, cue: str, facts: dict | None = None) -> str:
        facts = dict(facts or {})
        extra = set(facts) - CUE_FACTS[cue]
        if extra:
            raise ValueError(f"cue {cue} may not carry {sorted(extra)}")
        self._n_tokens += 1
        token = f"t-{self._n_tokens}"
        if self.mc_enabled:
            self._live.add(token)
            self._out.append(McSay(token, cue, facts))
            if not self.status_from_playback:
                self._set_mc("speaking")
        return token

    def token_live(self, token: str | None) -> bool:
        return token is not None and token in self._live

    def retire(self, token: str | None) -> None:
        if token is not None and token in self._live:
            self._live.discard(token)
            if not self._live and self.mc_status == "speaking":
                self._set_mc("idle")

    def interrupt_mc(self, reason: str) -> bool:
        """Cut the MC now. Returns True if something was live."""
        was = bool(self._live)
        self._live.clear()
        self._out.append(McInterrupt(reason))
        if self.mc_status in ("speaking", "listening"):
            self._set_mc("idle")
        return was

    def _set_mc(self, status: str) -> None:
        if status != self.mc_status:
            self.mc_status = status
            self.emit("mc.status", {"status": status})

    def listen(self, seat: int, purpose: str, attempt: int, deadline: int) -> str | None:
        if not self.voice_input:
            return None
        self._n_listens += 1
        lid = f"l-{self._n_listens}"
        self._out.append(McListen(lid, seat, purpose, attempt, deadline))
        if not self._live:
            self._set_mc("listening")
        return lid

    def stop_listen(self, listen_id: str | None) -> None:
        if listen_id is not None:
            self._out.append(McStopListen(listen_id))
            if self.mc_status == "listening":
                self._set_mc("idle")

    def set_mic(self, open_: bool, reason: str) -> None:
        if open_ != self._mic_open:
            self._mic_open = open_
            self._out.append(McMic(open_, reason))

    # ------------------------------------------------------------------ driving the generator
    def _drive(self, trigger: str | None, first: bool = False) -> None:
        if self._running:
            return
        self._running = True
        try:
            while self._gen is not None:
                try:
                    w = next(self._gen) if first else self._gen.send(trigger)
                except StopIteration:
                    self._gen = None
                    self._wait = None
                    return
                first = False
                self._wait = w
                if w.ready is not None and w.ready():
                    trigger = "ready"
                elif w.until is not None and w.until <= self.now():
                    trigger = "timeout"
                else:
                    return
        finally:
            self._running = False

    def _check(self) -> None:
        w = self._wait
        if self._running or self._gen is None or w is None:
            return
        if w.ready is not None and w.ready():
            self._drive("ready")
        elif w.until is not None and w.until <= self.now():
            self._drive("timeout")

    # ------------------------------------------------------------------ lobby
    def join(self, name: str) -> Result:
        if self.phase != "lobby":
            return Result(False, "SHOW IN PROGRESS")
        name = (name or "").strip() if isinstance(name, str) else ""
        if not name:
            return Result(False, "TYPE A NAME")
        if len(name) > NAME_MAX:
            return Result(False, "NAME TOO LONG")
        if any(unicodedata.category(c).startswith("C") for c in name):
            return Result(False, "NO NAMES LIKE THAT")
        key = normalize(name)
        if not key:
            return Result(False, "NO NAMES LIKE THAT")
        if any(normalize(p.name) == key for p in self.players.values()):
            return Result(False, "THAT NAME IS TAKEN")
        free = [s for s in JOIN_ORDER if s not in self.players]
        if not free:
            return Result(False, "HOUSE FULL")
        seat = free[0]
        used = {p.fan for p in self.players.values()}
        fan = self.rng.choice([f for f in FANS if f not in used])
        self._joined += 1
        p = Player(seat=seat, id=f"p-{self._joined}", name=name, fan=fan, credential=self._token_factory())
        self.players[seat] = p
        self.mode = "competitive" if len(self.players) > 1 else "solo"
        self.emit("seat.joined", {"seat": seat, "player": views.player_wire(self, p)})
        self._check()
        return Result(True, data={"seat": seat, "credential": p.credential, "playerId": p.id, "fanType": fan})

    def seat_for_credential(self, credential: str) -> int | None:
        for seat, p in self.players.items():
            if _secrets.compare_digest(p.credential.encode(), str(credential).encode()):
                return seat
        return None

    def start(self) -> Result:
        if self.phase != "lobby" or self._gen is not None:
            return Result(False, "SHOW ALREADY STARTED")
        if not self.players:
            return Result(False, "NEED A PLAYER")
        from . import flow  # local import: flow depends on this module

        self.mode = "competitive" if len(self.players) > 1 else "solo"
        self._gen = flow.game(self)
        self._drive(None, first=True)
        return Result(True)

    def phone_connection(self, seat: int, connected: bool) -> None:
        p = self.players.get(seat)
        if p is None or p.connected == connected:
            return
        p.connected = connected
        self.emit("seat.connection", {"seat": seat, "connected": connected})
        self._check()

    # ------------------------------------------------------------------ stage intake
    def stage_hello(self, conn: str, role: str, last_sseq: int | None = None) -> str:
        """Register a stage socket. Returns the effective role. Always answers with a snapshot."""
        effective = "viewer"
        notice = None
        if role == "primary":
            if self.primary is None or self.primary == conn:
                self.primary = conn
                effective = "primary"
            else:
                notice = {"proto": PROTO, "type": "error",
                          "data": {"code": "primary_taken", "message": "another stage is the primary; this one is a viewer"}}
        self._conns[conn] = effective
        self._out.append(StageDirect(conn, self.snapshot()))
        if notice:
            self._out.append(StageDirect(conn, notice))
        return effective

    def stage_disconnect(self, conn: str) -> None:
        self._conns.pop(conn, None)
        if self.primary == conn:
            self.primary = None

    def stage_roles(self) -> dict[str, str]:
        """conn -> effective role, primary first (used to re-register sockets on a new game)."""
        return dict(sorted(self._conns.items(), key=lambda kv: kv[1] != "primary"))

    def has_primary(self) -> bool:
        return self.primary is not None

    def _direct_error(self, conn: str, code: str, message: str) -> None:
        self._out.append(StageDirect(conn, {"proto": PROTO, "type": "error", "data": {"code": code, "message": message}}))

    def stage_message(self, conn: str, msg: dict) -> None:
        if not isinstance(msg, dict) or not isinstance(msg.get("data", {}), dict):
            return self._direct_error(conn, "bad_message", "not a stage message")
        t = msg.get("type")
        d = msg.get("data", {})
        role = self._conns.get(conn)
        if role is None:
            return self._direct_error(conn, "hello_required", "send stage.hello first")
        if t == "stage.ping":
            ct = d.get("clientTime")
            if isinstance(ct, (int, float)) and not isinstance(ct, bool):
                self._out.append(StageDirect(conn, {"proto": PROTO, "type": "pong",
                                                    "data": {"clientTime": ct, "serverTime": self.now()}}))
            return
        if t == "stage.need_snapshot":
            self._out.append(StageDirect(conn, self.snapshot()))
            return
        if role != "primary":
            return  # viewers' replies are ignored
        if t == "stage.beat_done":
            self._on_beat_done(conn, d)
        elif t == "stage.media_ready":
            ids = d.get("assetIds")
            if isinstance(ids, list):
                self.media_ready.update(i for i in ids if isinstance(i, str))
        elif t == "stage.media_ended":
            self._on_media_ended(d)
        self._check()

    def _on_beat_done(self, conn: str, d: dict) -> None:
        gid, sseq = d.get("gate"), d.get("sseq")
        g = self.gate
        if g is None or gid != g.id:
            return self._direct_error(conn, "unknown_gate", f"{gid} is not open")
        if sseq != g.sseq:
            return self._direct_error(conn, "gate_mismatch", f"{gid} has sseq {g.sseq}")
        if g.acked:
            return  # duplicate ack
        self._ack_gate(g)

    def _on_media_ended(self, d: dict) -> None:
        r = self.round
        if not isinstance(r, BuzzRound) or r.clip is None or r.media_end is not None:
            return  # stale or duplicate
        level, start, end = r.clip
        asset = self.q.track.asset_id if self.q and self.q.track else None
        reason, pos = d.get("reason"), d.get("positionSec")
        if d.get("assetId") != asset or d.get("level") != level or reason not in ("ended", "interrupted", "error"):
            return
        if not isinstance(pos, (int, float)) or isinstance(pos, bool):
            return
        if r.interrupt_pending:
            r.media_end = (reason, float(pos))  # any end resolves a buzz interrupt
        elif r.media_playing and reason == "interrupted":
            return  # the stage stopped on its own: not ours to act on; the watchdog covers it
        elif r.media_playing and (reason == "error" or abs(pos - end) <= self.cfg.media_end_tolerance_sec):
            r.media_end = (reason, float(pos))
        # anything else (wrong position) is a stale end and ignored

    # ------------------------------------------------------------------ phone inputs
    def phone_action(self, seat: int, action: dict) -> Result:
        p = self.players.get(seat)
        if p is None:
            return Result(False, "no_such_player")
        if not isinstance(action, dict) or not isinstance(action.get("type"), str):
            return Result(False, "bad_input")
        if not p.connected:
            return Result(False, "disconnected")
        handler = {
            "ox": self._a_ox, "buzz": self._a_buzz, "text_answer": self._a_text_answer,
            "choose_typing": self._a_choose_typing, "betrayal_reason": self._a_reason,
            "betrayal_decision": self._a_decision, "bet": self._a_bet, "final_choice": self._a_final_choice,
        }.get(action["type"])
        if handler is None:
            return Result(False, "bad_input")
        res = handler(p, action)
        if res.ok:
            self._touch(seat)
            self._check()
        return res

    def _a_ox(self, p: Player, a: dict) -> Result:
        r = self.round
        if self.phase != "ox.answering" or not isinstance(r, OxRound):
            return Result(False, "not_now")
        if a.get("choice") not in ("O", "X"):
            return Result(False, "bad_input")
        if p.seat in r.picks:
            return Result(False, "already_answered")
        r.picks[p.seat] = a["choice"]
        self.emit("ox.submitted", {"seat": p.seat})
        return Result(True)

    def _a_buzz(self, p: Player, a: dict) -> Result:
        r = self.round
        if isinstance(r, BuzzRound) and r.holder is not None:
            return Result(False, "busy")
        if not isinstance(r, BuzzRound) or not r.armed or self.phase not in (
                "buzzer.reading", "buzzer.open", "buzzer.media"):
            return Result(False, "not_now")
        if p.seat in r.locked:
            return Result(False, "locked_out")
        mc_int = bool(self._live)
        media_int = r.media_playing
        r.holder = p.seat
        r.armed = False
        if mc_int:
            self.interrupt_mc("buzz")  # also makes the reading token stale
        if media_int:
            r.interrupt_pending = True
            r.interrupted_at = self.now()
            r.media_playing = False
        self.emit("buzzer.pressed", {"seat": p.seat, "mediaInterrupted": media_int, "mcInterrupted": mc_int})
        return Result(True)

    def _a_text_answer(self, p: Player, a: dict) -> Result:
        r = self.round
        if not isinstance(r, BuzzRound) or self.phase != "buzzer.answering" or r.holder != p.seat:
            return Result(False, "not_holder")
        if not r.text_box:
            return Result(False, "not_now")
        text = a.get("text")
        if not isinstance(text, str):
            return Result(False, "bad_input")
        text = "".join(c for c in text if not unicodedata.category(c).startswith("C")).strip()
        if not text or len(text) > self.cfg.text_answer_max:
            return Result(False, "bad_input")
        if r.answer is not None:
            return Result(False, "already_answered")
        r.answer = (text, "phone")
        return Result(True)

    def _a_choose_typing(self, p: Player, a: dict) -> Result:
        r = self.round
        if not isinstance(r, BuzzRound) or self.phase != "buzzer.answering" or r.holder != p.seat or r.answer is not None:
            return Result(False, "not_holder")
        r.text_box = True
        self.stop_listen(r.listen_id)
        r.listen_id = None
        return Result(True)

    def _a_reason(self, p: Player, a: dict) -> Result:
        r = self.round
        b = r.betrayal if isinstance(r, OxRound) else None
        if b is None or b.seat != p.seat or b.step != "reason":
            return Result(False, "not_now")
        if a.get("reason") not in BETRAYAL_REASONS:
            return Result(False, "bad_input")
        if b.reason is not None:
            return Result(False, "already_answered")
        b.reason, b.reason_source = BETRAYAL_REASONS[a["reason"]], "phone"
        return Result(True)

    def _a_decision(self, p: Player, a: dict) -> Result:
        r = self.round
        b = r.betrayal if isinstance(r, OxRound) else None
        if b is None or b.seat != p.seat or b.step != "decision":
            return Result(False, "not_now")
        if type(a.get("switch")) is not bool:
            return Result(False, "bad_input")
        if b.decision is not None:
            return Result(False, "already_answered")
        b.decision = a["switch"]
        return Result(True)

    def _a_bet(self, p: Player, a: dict) -> Result:
        r = self.round
        if self.phase != "final.betting" or not isinstance(r, FinalRound):
            return Result(False, "not_now")
        if p.seat in r.bet_placed:
            return Result(False, "already_answered")
        if not scoring.is_valid_bet(a.get("amount"), p.score):
            return Result(False, "bad_input")
        r.bets[p.seat] = a["amount"]
        r.bet_placed.add(p.seat)
        self.emit("final.bet_placed", {"seat": p.seat})
        return Result(True)

    def _a_final_choice(self, p: Player, a: dict) -> Result:
        r = self.round
        if self.phase != "final.answering" or not isinstance(r, FinalRound):
            return Result(False, "not_now")
        if a.get("choice") not in ("A", "B", "C", "D"):
            return Result(False, "bad_input")
        if p.seat in r.answer_placed:
            return Result(False, "already_answered")
        r.choices[p.seat] = a["choice"]
        r.answer_placed.add(p.seat)
        self.emit("final.answer_placed", {"seat": p.seat})
        return Result(True)

    def phone_view(self, seat: int) -> dict | None:
        return views.phone_view(self, seat)

    # ------------------------------------------------------------------ MC inputs
    def mc_played(self, token: str) -> bool:
        """The MC output cursor reached the end of this line. Stale tokens are ignored."""
        if token not in self._live:
            return False
        self.retire(token)
        self._check()
        return True

    def mc_failed(self, token: str) -> bool:
        return self.mc_played(token)

    def mc_started(self, token: str) -> bool:
        """The browser began playing this line (live MC): the ghost starts talking now."""
        if token not in self._live:
            return False
        if self.status_from_playback:
            self._set_mc("speaking")
        return True

    def mc_offline(self) -> None:
        """The live MC is gone: pending lines end now, later lines resolve at once, the holder types."""
        self.mc_enabled = False
        self.voice_input = False
        self._live.clear()
        if self.mc_status in ("speaking", "listening"):
            self._set_mc("idle")
        r = self.round
        if isinstance(r, BuzzRound) and self.phase == "buzzer.answering" and r.answer is None:
            r.text_box, r.listen_id = True, None
            self._touch_all()
        if isinstance(r, OxRound) and r.betrayal is not None:
            r.betrayal.listen_id = None
        self._check()

    def mc_online(self, voice_input: bool = True) -> None:
        """The live MC is connected: it speaks and listens, and `speaking` follows real playback."""
        self.mc_enabled = True
        self.voice_input = voice_input
        self.status_from_playback = True

    def mc_mock(self) -> None:
        """Back to the mock MC (public mode, after the live MC stopped): lines are timed, nothing is heard."""
        self.mc_enabled = True
        self.voice_input = False
        self.status_from_playback = False

    def mc_voice_answer(self, listen_id: str, heard: str, recognition: str, voiced: bool) -> bool:
        r = self.round
        if not isinstance(r, BuzzRound) or listen_id is None or r.listen_id != listen_id or r.holder is None \
                or r.answer is not None or self.phase != "buzzer.answering":
            return False
        r.listen_id = None
        seat = r.holder
        text = heard.strip()[:HEARD_MAX] if isinstance(heard, str) else ""
        if recognition == "clear" and voiced is True and text:
            r.answer = (text, "voice")
            if self.mc_status == "listening":
                self._set_mc("idle")
        else:  # recognition failure, never a wrong answer
            r.failures += 1
            name = self.players[seat].name
            if r.failures < self.cfg.voice_attempts:
                self.say("ask_again", {"name": name, "attempt": r.failures + 1})
                r.listen_attempt += 1
                r.listen_id = self.listen(seat, "answer", r.listen_attempt, r.answer_deadline or self.now())
            else:
                r.text_box = True
                self.say("phone_fallback", {"name": name})
                if self.mc_status == "listening":
                    self._set_mc("idle")
            self._touch(seat)
        self._check()
        return True

    def mc_voice_reason(self, listen_id: str, heard: str) -> bool:
        r = self.round
        b = r.betrayal if isinstance(r, OxRound) else None
        if b is None or b.step != "reason" or b.reason is not None or listen_id is None or b.listen_id != listen_id:
            return False
        text = heard.strip()[:HEARD_MAX] if isinstance(heard, str) else ""
        if not text:
            return False
        b.reason, b.reason_source = text, "voice"
        b.listen_id = None
        self._check()
        return True

    def mc_voice_decision(self, listen_id: str, switch: bool | None) -> bool:
        r = self.round
        b = r.betrayal if isinstance(r, OxRound) else None
        if b is None or b.step != "decision" or b.decision is not None or listen_id is None or b.listen_id != listen_id:
            return False
        if type(switch) is not bool:
            return False  # unclear speech: keep listening until the window ends
        b.decision = switch
        b.listen_id = None
        self._check()
        return True

    def mc_caption(self, utterance_id: int | str, text: str, final: bool) -> bool:
        """Filter and forward the MC's own words. Never pass player speech here."""
        try:
            uid = f"u-{int(str(utterance_id).removeprefix('u-'))}"
        except ValueError:
            return False
        if not isinstance(text, str):
            return False
        out = self._captions.process(uid, text, bool(final), self._caption_secrets())
        if out is None:
            return False
        self.emit("mc.caption", {"utteranceId": uid, "text": out, "final": bool(final)})
        return True

    def _caption_secrets(self) -> CaptionSecrets:
        q = self.q
        if q is None or self.revealed_answer is not None:
            return CaptionSecrets()
        phrases = [q.explanation]
        if q.kind in ("buzzer", "av"):
            phrases += [q.answer, *q.aliases]
        if q.kind == "av" and q.track:
            c = q.track.credit
            phrases += [x for x in (c.title, c.author, c.performer) if x]
        if q.kind == "final" and q.choices:
            phrases.append(q.choices["ABCD".index(q.answer)])
        letter = "ox" if q.kind == "ox" else "letters" if q.kind == "final" else None
        return CaptionSecrets(phrases=tuple(p for p in phrases if p), letter_kind=letter,
                              block_all=q.kind == "buzzer" and not self.q_text_visible)

    # ------------------------------------------------------------------ helpers used by flow
    def public_question(self) -> dict | None:
        return views.public_question(self)

    def begin_answer(self, r: BuzzRound, seat: int, deadline: int) -> None:
        r.answer = None
        r.failures = 0
        r.text_box = not self.voice_input
        r.answer_deadline = deadline
        r.listen_attempt = 1
        r.listen_id = self.listen(seat, "answer", 1, deadline)
        self._touch(seat)

    def end_answer(self, r: BuzzRound) -> None:
        if r.listen_id is not None:
            self.stop_listen(r.listen_id)
            r.listen_id = None
        if self.mc_status == "listening":
            self._set_mc("idle")
        r.text_box = False
        self.input_deadline = None
        self._touch_all()

    def settle(self, q: Question, deltas: dict[int, int]) -> dict:
        """Apply score changes exactly once per question; returns the `score.settled` payload data."""
        if q.id in self._settled:
            raise RuntimeError(f"{q.id} already settled")
        self._settled.add(q.id)
        before = scoring.leaders(self.scores())
        for seat, d in deltas.items():
            self.players[seat].score += d
            if self.players[seat].score < 0:
                raise RuntimeError("no negative balances")
        after_scores = self.scores()
        ranks = scoring.rank_scores(after_scores)
        out = [{"seat": s, "delta": deltas.get(s, 0), "score": after_scores[s], "rank": ranks[s]} for s in sorted(self.players)]
        return {"deltas": out, "leadChange": scoring.leaders(after_scores) != before}
