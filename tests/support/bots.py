"""Scripted players for simulation tests. Each decision is a function so a test can script it exactly."""
from __future__ import annotations

from khqs.engine.rounds import BuzzRound, FinalRound, OxRound


class Bots:
    """Acts once per (kind, question, seat). Install with `Bots(sim, ...)`; it hooks into the sim loop.

    ox(seat, qnum)        -> 'O' | 'X' | None (None = never answers)
    buzz(qnum, level)     -> seat that buzzes in this window, or None
    voice(qnum, seat, n)  -> (heard, recognition, voiced) for the n-th voice attempt, or None to stay silent
    text(qnum, seat)      -> typed answer or None
    reason(seat) / decision(seat) -> reason id / bool or None
    bet(seat, score) -> int or None ; choice(seat) -> 'A'..'D' or None
    """

    def __init__(self, sim, *, ox=None, buzz=None, voice=None, text=None, reason=None, decision=None, bet=None,
                 choice=None, voice_delay=1500, think_ms=500):
        self.sim = sim
        self.ox = ox or (lambda seat, q: "O")
        self.buzz = buzz or (lambda q, level: None)
        self.voice = voice or (lambda q, seat, n: None)
        self.text = text or (lambda q, seat: None)
        self.reason = reason or (lambda seat: "hunch")
        self.decision = decision or (lambda seat: False)
        self.bet = bet or (lambda seat, score: 0)
        self.choice = choice or (lambda seat: "A")
        self.voice_delay, self.think_ms = voice_delay, think_ms
        self.done: set = set()
        self.voice_n: dict = {}
        self._seen_listens = 0
        sim.hooks.append(self._on)

    def _once(self, key):
        if key in self.done:
            return False
        self.done.add(key)
        return True

    def _later(self, fn):
        self.sim.after(self.think_ms, fn)

    def _on(self, sim):
        eng = sim.eng
        r, q = eng.round, eng.q
        if eng.phase == "ox.answering" and isinstance(r, OxRound):
            for seat in sorted(eng.players):
                c = self.ox(seat, q.number)
                if c and self._once(("ox", q.number, seat)):
                    self._later(lambda s=seat, c=c: sim.act(s, {"type": "ox", "choice": c}))
        if eng.phase == "ox.betrayal" and isinstance(r, OxRound) and r.betrayal:
            b = r.betrayal
            if b.step == "reason" and self._once(("reason", q.number)):
                rid = self.reason(b.seat)
                if rid:
                    self._later(lambda: sim.act(b.seat, {"type": "betrayal_reason", "reason": rid}))
            if b.step == "decision" and self._once(("decision", q.number)):
                d = self.decision(b.seat)
                if d is not None:
                    self._later(lambda: sim.act(b.seat, {"type": "betrayal_decision", "switch": d}))
        if isinstance(r, BuzzRound) and r.armed and eng.phase in ("buzzer.reading", "buzzer.open", "buzzer.media"):
            seat = self.buzz(q.number, r.level)
            if seat is not None and self._once(("buzz", q.number, r.level, len(r.attempts), eng.phase)):
                self._later(lambda: sim.act(seat, {"type": "buzz"}))
        if isinstance(r, BuzzRound) and eng.phase == "buzzer.answering" and r.holder is not None:
            seat = r.holder
            t = self.text(q.number, seat)
            if r.text_box and t and self._once(("text", q.number, seat, len(r.attempts))):
                self._later(lambda: sim.act(seat, {"type": "text_answer", "text": t}))
        while self._seen_listens < len(sim.listens):
            l = sim.listens[self._seen_listens]
            self._seen_listens += 1
            if l.purpose == "answer":
                n = self.voice_n.get((q.number, l.seat), 0) + 1
                self.voice_n[(q.number, l.seat)] = n
                v = self.voice(q.number, l.seat, n)
                if v is not None:
                    sim.after(self.voice_delay, lambda l=l, v=v: eng.mc_voice_answer(l.listen_id, *v) and sim.pump())
        if eng.phase == "final.betting" and isinstance(r, FinalRound):
            for seat, p in sorted(eng.players.items()):
                b = self.bet(seat, p.score)
                if b is not None and self._once(("bet", seat)):
                    self._later(lambda s=seat, b=b: sim.act(s, {"type": "bet", "amount": b}))
        if eng.phase == "final.answering" and isinstance(r, FinalRound):
            for seat in sorted(eng.players):
                c = self.choice(seat)
                if c and self._once(("choice", seat)):
                    self._later(lambda s=seat, c=c: sim.act(s, {"type": "final_choice", "choice": c}))
