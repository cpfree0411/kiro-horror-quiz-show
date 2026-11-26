#!/usr/bin/env python
"""Worst-case length of the music question, with the mock MC's line timings (P7).

Runs the engine on a fake clock (no sockets, no sleeping). The adversary lets every clip play to its end, buzzes at the
last 100 ms of every open window, holds the buzzer until 100 ms before the answer window ends and then (when hints exist)
asks for a hint, with nobody voting, so every consent window runs its full 8 s. The fake stage acks every gate after
`--ack` ms. MC lines last what the mock MC would take (60 ms per character, 0.9 to 6 s).

Run from a checkout (also works on an older checkout that has no hints, to compare):
    PYTHONPATH=server:tests python -B scripts/music_timing.py [--no-hints] [--refuse] [--ack 1500]
"""
from __future__ import annotations

import argparse
import sys

from khqs.engine.rounds import BuzzRound
from khqs.mc import mock

from support.bots import Bots
from support.content_fixture import BANK
from support.harness import new_sim
from support.seeds import seed_for_track


def line_ms(cue, facts):
    return mock.MockMc(None).duration_ms(cue, facts, mock.line_for(cue, facts))


def say_table(track, names):
    n = names[0]
    t = {"*": 1200}
    cues = {
        "intro_music": {"number": 5, "category": "Midnight Concert"},
        "suspense": {"kind": "av"},
        "react_judge": {"name": n, "correct": False},
        "react_answer": {"kind": "av", "answer": track.answer, "explanation": track.explanation, "results": []},
        "longer_listen": {"level": 1, "max_level": 2},
        "hint_ask": {"name": n},
        "hint_refused": {"name": n},
        "hint_none": {"name": n, "why": "used"},
    }
    for cue, facts in cues.items():
        try:
            t[cue] = line_ms(cue, facts)
        except (KeyError, ValueError, TypeError):
            pass
    try:  # the pre-P7 tree: one long line with the clue
        t["hint_line"] = max(line_ms("hint_line", {"level": i + 1, "max_level": 2, "clue": c}) for i, c in enumerate(track.clues))
    except (KeyError, ValueError, TypeError):
        pass
    try:  # P7: the longest grant line over every hint, with the longest opener
        t["hint_grant"] = max(line_ms("hint_grant", {"name": n, "how": how, "kind": kind, "text": text, "number": i + 1})
                              for i, (kind, text) in enumerate(track.hints) for how in ("solo", "agreed", "silence"))
    except (KeyError, ValueError, TypeError, AttributeError):
        pass
    return t


def run(use_hints: bool, ack_ms: int, names=("Mina", "Junho", "Ray"), refuse=False):
    track = BANK.tracks[0]
    sim = new_sim(BANK, names=names, seed=seed_for_track("dm"), ack_ms=ack_ms, say_ms=say_table(track, names))
    Bots(sim, ox=lambda s, n: "O" if s == 0 else "X")
    done = set()

    def hook(s):
        e, r = s.eng, s.eng.round
        if not isinstance(r, BuzzRound) or e.q is None or e.q.kind != "av":
            return
        if e.phase == "buzzer.open" and r.armed and r.holder is None and e.deadline:
            seat = next((x for x in sorted(e.players) if x not in r.locked), None)
            key = ("buzz", e.deadline, r.level)
            if seat is not None and key not in done:
                done.add(key)
                s.after(max(0, e.deadline - s.clock.now_ms() - 100), lambda seat=seat: s.act(seat, {"type": "buzz"}))
        if use_hints and e.phase == "buzzer.answering" and r.holder is not None and r.answer is None and not r.hint_request \
                and e.can_ask_hint(r.holder):
            key = ("hint", e.deadline, r.holder)
            if key not in done:
                done.add(key)
                seat = r.holder
                s.after(max(0, e.deadline - s.clock.now_ms() - 100), lambda seat=seat: s.act(seat, {"type": "hint"}))
        if refuse and e.phase == "buzzer.hint" and r.consent is not None and ("no", e.deadline, r.hints_given, len(r.hint_asked)) not in done:
            done.add(("no", e.deadline, r.hints_given, len(r.hint_asked)))
            voter = r.consent.voters[0]
            s.after(max(0, r.consent.deadline - s.clock.now_ms() - 100), lambda v=voter: s.act(v, {"type": "hint_vote", "agree": False}))
    sim.hooks.append(hook)
    sim.run_until(lambda: any(m["type"] == "av.play" for m in sim.stream))
    t0 = next(t for m, t in zip(sim.stream, sim.stream_t) if m["type"] == "question.presented" and m["data"]["question"]["kind"] == "av")
    sim.run_until(lambda: sum(m["type"] == "score.settled" for m in sim.stream) >= 5, timeout_ms=3_600_000)
    t1 = next(t for m, t in zip(sim.stream, sim.stream_t) if m["type"] == "score.settled" and m["sseq"] > next(
        x["sseq"] for x in sim.stream if x["type"] == "answer.revealed" and x["data"]["questionId"] == "q-av-05")) + ack_ms
    attempts = len(sim.eng.round.attempts) if isinstance(sim.eng.round, BuzzRound) else 0
    cues = [e.cue for _, e, _ in sim.mc_fx if hasattr(e, "cue")]
    return {"seconds": (t1 - t0) / 1000, "plays": [m["data"]["level"] for m in sim.stream if m["type"] == "av.play"],
            "hint_asks": cues.count("hint_ask"), "grants": cues.count("hint_grant"), "refusals": cues.count("hint_refused"),
            "answers": sum(1 for m in sim.stream if m["type"] == "buzzer.judged") - 0, "attempts_last": attempts}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-hints", action="store_true")
    ap.add_argument("--refuse", action="store_true", help="the first voter says NO at the last moment of every consent window")
    ap.add_argument("--ack", type=int, default=1500)
    a = ap.parse_args()
    sys.dont_write_bytecode = True
    r = run(not a.no_hints, a.ack, refuse=a.refuse)
    print(f"music question, worst case: {r['seconds']:.1f} s ({r['seconds'] / 60:.1f} min); clips played {r['plays']}; "
          f"hint asks {r['hint_asks']}, granted {r['grants']}, refused {r['refusals']}; every answer window ran out")
