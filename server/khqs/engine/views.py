"""Projections of engine state. Public (stage/snapshot) and private (one player's phone).

Both builders read an explicit allow-list of fields. Secret state (picks, bets, reasons,
credentials, answers) is read only for the player's own view, and only their own entries.
"""
from __future__ import annotations

from ..rules import scoring
from .rounds import BETRAYAL_REASONS, BuzzRound, FinalRound, OxRound

QUESTION_TOTAL = 8


def player_wire(eng, p) -> dict:
    return {"id": p.id, "name": p.name, "fanType": p.fan, "score": p.score,
            "rank": eng.ranks()[p.seat], "connected": p.connected}


def seats_wire(eng) -> list[dict]:
    ranks = eng.ranks()
    out = []
    for s in (0, 1, 2):
        p = eng.players.get(s)
        if p is None:
            out.append({"seat": s, "status": "vacant", "player": None})
        else:
            out.append({"seat": s, "status": "occupied",
                        "player": {"id": p.id, "name": p.name, "fanType": p.fan, "score": p.score,
                                   "rank": ranks[s], "connected": p.connected}})
    return out


def public_question(eng) -> dict | None:
    q = eng.q
    if q is None:
        return None
    hidden = q.kind == "buzzer" and not eng.q_text_visible
    media = {"assetId": q.track.asset_id, "mediaType": "audio"} if q.kind == "av" and q.track else None
    return {
        "id": q.id, "kind": q.kind, "number": q.number, "act": q.act, "indexInAct": q.index_in_act,
        "category": q.category, "text": None if hidden else q.text, "textHidden": hidden,
        "choices": list(q.choices) if q.kind == "final" and q.choices else None,
        "media": media, "hintLevel": eng.hint_level, "maxHintLevel": 2 if q.kind == "av" else 0,
    }


def _betrayal_public(b) -> dict | None:
    if b is None:
        return None
    return {"seat": b.seat, "selection": b.selection, "status": b.status, "from": b.from_, "to": b.to}


def round_public(eng) -> dict | None:
    r = eng.round
    if isinstance(r, OxRound):
        return {"kind": "ox", "submitted": sorted(r.picks),
                "revealedChoices": None if r.revealed is None else [dict(c) for c in r.revealed],
                "unanimousStreak": eng.ox_streak, "betrayal": _betrayal_public(r.betrayal)}
    if isinstance(r, BuzzRound):
        return {"kind": "buzzer", "buzzerOpen": r.armed, "holder": r.holder, "lockedOut": sorted(r.locked),
                "attempts": [{"seat": s, "correct": c} for s, c in r.attempts], "mediaPlaying": r.media_playing}
    if isinstance(r, FinalRound):
        return {"kind": "final", "category": r.category, "betPlaced": sorted(r.bet_placed),
                "answerPlaced": sorted(r.answer_placed),
                "revealedChoices": None if r.revealed_choices is None else [dict(c) for c in r.revealed_choices],
                "revealedBets": None if r.revealed_bets is None else [dict(b) for b in r.revealed_bets]}
    return None


def snapshot_data(eng) -> dict:
    return {
        "game": {"id": eng.game_id, "mode": eng.mode, "act": 4 if eng.phase == "ended" else eng.act,
                 "phase": eng.phase, "phaseStartedAt": eng.phase_started_at, "deadline": eng.deadline,
                 "questionNo": eng.question_no, "questionTotal": QUESTION_TOTAL},
        "seats": seats_wire(eng),
        "question": public_question(eng),
        "round": round_public(eng),
        "mc": {"status": eng.mc_status},
        "openGate": {"id": eng.gate.id, "type": eng.gate.type} if eng.gate else None,
        "revealedAnswer": eng.revealed_answer,
    }


def phone_view(eng, seat: int) -> dict | None:
    """What one player's phone may know. Only this player's own picks and bets appear."""
    p = eng.players.get(seat)
    if p is None:
        return None
    r = eng.round
    q = eng.q
    screen = "waiting"
    own: dict = {}
    if eng.phase == "lobby":
        screen = "waiting"
    elif eng.phase == "ended":
        screen = "done"
    elif eng.phase == "ox.answering" and isinstance(r, OxRound):
        screen = "ox_locked" if seat in r.picks else "ox"
        own["pick"] = r.picks.get(seat)
    elif isinstance(r, BuzzRound) and eng.phase in ("buzzer.reading", "buzzer.open", "buzzer.media"):
        if seat in r.locked:
            screen = "locked"
        elif r.armed and p.connected:
            screen = "buzzer"
        own["canBuzz"] = r.armed and seat not in r.locked and p.connected
    elif isinstance(r, BuzzRound) and eng.phase == "buzzer.answering":
        if r.holder == seat:
            screen = "answer_text" if r.text_box else "answer_voice"
            own["textBox"] = r.text_box
            if q is not None and q.kind == "av":
                own["canHint"] = eng.can_ask_hint(seat) and not r.hint_request
        elif seat in r.locked:
            screen = "locked"
    elif isinstance(r, BuzzRound) and eng.phase == "buzzer.hint" and r.holder is not None:
        # a spoken hint was requested: the requester waits, the others vote while the window is open
        c = r.consent
        if r.holder == seat:
            screen = "hint_wait"
            own["hint"] = {"asking": c is not None}
        elif c is not None and seat in c.voters:
            screen = "hint_voted" if seat in c.votes else "hint_vote"
            own["hint"] = {"requester": eng.players[c.seat].name, "voted": c.votes.get(seat)}
    elif isinstance(r, OxRound) and eng.phase == "ox.betrayal" and r.betrayal and r.betrayal.seat == seat \
            and r.betrayal.step:
        b = r.betrayal
        screen = "betrayal_reason" if b.step == "reason" else "betrayal_decision"
        own["betrayal"] = {"step": b.step, "from": b.from_,
                           "reasons": [{"id": k, "label": v} for k, v in BETRAYAL_REASONS.items()]}
    elif eng.phase == "final.betting" and isinstance(r, FinalRound):
        screen = "bet_locked" if seat in r.bet_placed else "bet"
        own["maxBet"] = p.score
        own["bet"] = r.bets.get(seat)
    elif eng.phase == "final.answering" and isinstance(r, FinalRound):
        screen = "final_locked" if seat in r.answer_placed else "final_choice"
        own["choice"] = r.choices.get(seat)
    return {
        "game": {"id": eng.game_id, "phase": eng.phase, "act": 4 if eng.phase == "ended" else eng.act,
                 "mode": eng.mode, "serverTime": eng.now(), "deadline": eng.input_deadline},
        "you": {"seat": seat, "name": p.name, "fanType": p.fan, "score": p.score,
                "rank": eng.ranks()[seat], "connected": p.connected},
        "screen": screen,
        "question": public_question(eng),
        "own": own,
    }
