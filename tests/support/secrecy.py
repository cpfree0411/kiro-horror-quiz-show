"""Secrecy scan over every channel of a finished or running simulation.

A secret is something that must not leave the engine before its reveal event: the answer, aliases,
explanation, music credits, buzzer text, picks and bets. Channels scanned: every stage stream message,
every snapshot taken after each step, every player's phone view, every MC command, and (separately)
log records.
"""
from __future__ import annotations

import json
import re

from khqs.engine.effects import McListen, McSay


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).casefold()


def question_secrets(q) -> list[str]:
    out = [q.explanation]
    if q.kind in ("buzzer", "av"):
        out += [q.answer, *q.aliases]
    if q.kind == "av" and q.track:
        c = q.track.credit
        out += [x for x in (c.title, c.author, c.performer, c.source) if x]
    return [s for s in out if len(s) >= 3]


def hint_secrets(q) -> list[str]:
    """The private spoken hints of a music question: its clues and its composer. They are secret until the MC is handed them."""
    return [t for _kind, t in q.track.hints] if q.kind == "av" and q.track else []


def hint_grants(sim) -> dict[str, int]:
    """normalised hint text -> stream position of the first `hint_grant` cue that handed it to the MC."""
    out: dict[str, int] = {}
    for sseq_at, e, _t in sim.mc_fx:
        if isinstance(e, McSay) and e.cue == "hint_grant":
            out.setdefault(_norm(e.facts["text"]), sseq_at)
    return out


def _blob(x) -> str:
    return _norm(json.dumps(x, ensure_ascii=False))


def reveal_sseqs(sim) -> dict[str, int]:
    return {m["data"]["questionId"]: m["sseq"] for m in sim.stream if m["type"] == "answer.revealed"}


def assert_no_leaks(sim, canary_bets: dict[int, int] | None = None) -> None:
    content = sim.eng.content
    reveal = reveal_sseqs(sim)
    end = float("inf")
    problems: list[str] = []

    # --- answers, aliases, explanations, credits
    grants = hint_grants(sim)
    for q in content.questions:
        r = reveal.get(q.id, end)
        hints = {_norm(h) for h in hint_secrets(q)}
        secrets = [_norm(s) for s in question_secrets(q) if _norm(s) not in hints]
        # a clue or the composer is secret until the MC is handed it on request (the hint_grant cue); then it may appear in captions
        for h in sorted(hints):
            at = min(r, grants.get(h, end))
            if len(h) < 3:
                continue
            for m in sim.stream:
                if m["sseq"] < at and h in _blob(m["data"]):
                    problems.append(f"stream #{m['sseq']} {m['type']} leaks the hint {h!r} of {q.id}")
            for snap in sim.snapshots:
                if snap["sseq"] < at and h in _blob(snap["data"]):
                    problems.append(f"snapshot #{snap['sseq']} leaks the hint {h!r} of {q.id}")
            for sseq, views in sim.views:
                if sseq < at and h in _blob(views):
                    problems.append(f"phone view @{sseq} leaks the hint {h!r} of {q.id}")
            for sseq_at, e, _t in sim.mc_fx:
                if sseq_at < at and isinstance(e, (McSay, McListen)) and h in _blob(getattr(e, "facts", {})):
                    problems.append(f"MC {getattr(e, 'cue', 'listen')} @{sseq_at} leaks the hint {h!r} of {q.id}")
        # the text itself of a final's correct choice is public (it is on the board)
        for m in sim.stream:
            if m["sseq"] < r:
                b = _blob(m["data"])
                problems += [f"stream #{m['sseq']} {m['type']} leaks {s!r} of {q.id}" for s in secrets if s in b]
        for snap in sim.snapshots:
            if snap["sseq"] < r:
                b = _blob(snap["data"])
                problems += [f"snapshot #{snap['sseq']} leaks {s!r} of {q.id}" for s in secrets if s in b]
        for sseq, views in sim.views:
            if sseq < r:
                b = _blob(views)
                problems += [f"phone view @{sseq} leaks {s!r} of {q.id}" for s in secrets if s in b]
        for sseq_at, e, _t in sim.mc_fx:
            if sseq_at < r and isinstance(e, (McSay, McListen)):
                b = _blob(getattr(e, "facts", {}))
                problems += [f"MC {getattr(e, 'cue', 'listen')} @{sseq_at} leaks {s!r} of {q.id}" for s in secrets if s in b]

    # --- buzzer question text only after question.text_revealed
    revealed_text = {m["data"]["questionId"]: m["sseq"] for m in sim.stream if m["type"] == "question.text_revealed"}
    for q in content.questions:
        if q.kind != "buzzer":
            continue
        t = _norm(q.text)
        at = revealed_text.get(q.id, end)
        for m in sim.stream:
            if m["sseq"] < at and t in _blob(m["data"]):
                problems.append(f"stream #{m['sseq']} {m['type']} has the hidden text of {q.id}")
        for snap in sim.snapshots:
            if snap["sseq"] < at and t in _blob(snap["data"]):
                problems.append(f"snapshot #{snap['sseq']} has the hidden text of {q.id}")
        for sseq, views in sim.views:
            if sseq < at and t in _blob(views):
                problems.append(f"phone view @{sseq} has the hidden text of {q.id}")

    # --- picks: snapshots may only show what the stream already revealed
    ox_rev = [(m["sseq"], m["data"]["choices"]) for m in sim.stream if m["type"] == "ox.choices_revealed"]
    fin_rev = [(m["sseq"], m["data"]["choices"]) for m in sim.stream if m["type"] == "final.choices_revealed"]
    bet_rev = [(m["sseq"], {"seat": m["data"]["seat"], "bet": m["data"]["bet"], "allIn": m["data"]["allIn"]})
               for m in sim.stream if m["type"] == "final.bet_revealed"]
    for snap in sim.snapshots:
        rnd, s = snap["data"]["round"], snap["sseq"]
        if not rnd:
            continue
        if rnd["kind"] == "ox" and rnd["revealedChoices"] is not None:
            if not any(c == rnd["revealedChoices"] and sq <= s for sq, c in ox_rev):
                problems.append(f"snapshot #{s}: OX picks shown before ox.choices_revealed")
        if rnd["kind"] == "final":
            if rnd["revealedChoices"] is not None and not any(c == rnd["revealedChoices"] and sq <= s for sq, c in fin_rev):
                problems.append(f"snapshot #{s}: final picks shown before final.choices_revealed")
            shown = rnd["revealedBets"] or []
            sent = [b for sq, b in bet_rev if sq <= s]
            if shown != sent[: len(shown)] or len(shown) > len(sent):
                problems.append(f"snapshot #{s}: bets shown that the stream has not revealed")
    for m in sim.stream:  # picks and bets exist in the stream only in their reveal messages
        t = m["type"]
        if t in ("ox.submitted", "final.bet_placed", "final.answer_placed", "betrayal.listening") and set(m["data"]) != {"seat"}:
            problems.append(f"{t} #{m['sseq']} carries more than the seat")

    # --- bet canaries: a bet amount does not appear before its own reveal
    for seat, amount in (canary_bets or {}).items():
        at = next((m["sseq"] for m in sim.stream if m["type"] == "final.bet_revealed" and m["data"]["seat"] == seat), end)
        pat = re.compile(rf"(?<![\w.-]){amount}(?![\w.-])")
        for m in sim.stream:
            if m["sseq"] < at and pat.search(json.dumps(m["data"])):
                problems.append(f"bet {amount} of seat {seat} in stream #{m['sseq']} {m['type']}")
        for snap in sim.snapshots:
            if snap["sseq"] < at and pat.search(json.dumps(snap["data"])):
                problems.append(f"bet {amount} of seat {seat} in snapshot #{snap['sseq']}")
        for sseq, views in sim.views:
            for vs, v in views.items():
                if vs != seat and pat.search(json.dumps({k: x for k, x in v.items() if k != "game"})) and sseq < at:
                    problems.append(f"bet {amount} of seat {seat} in seat {vs}'s phone view @{sseq}")

    # --- credentials never leave
    creds = [p.credential for p in sim.eng.players.values()]
    everything = json.dumps([sim.stream, sim.snapshots, sim.views, [m for _, m in sim.directs]], ensure_ascii=False)
    for c in creds:
        if c in everything:
            problems.append("a credential appears in a public or phone channel")

    assert not problems, "\n".join(problems[:15])
