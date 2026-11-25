"""The show as one generator. It yields `Wait` objects and reads engine state when resumed.

Order of events follows docs/GAME_RULES.md and the scenario files in interface/scenarios.
"""
from __future__ import annotations

from ..rules import betrayal as btr
from ..rules import scoring
from ..rules.judge import answer_matches
from .rounds import BetrayalState, BuzzRound, FinalRound, OxRound
from .waits import Wait

ACT_TITLES = {1: "Act 1 · O/X", 2: "Act 2 · Buzzer", 3: "FINAL BET"}
MEDIA_READY_WAIT_MS = 10_000


# ---------------------------------------------------------------------------- shared helpers
def say_wait(eng, token):
    """Wait until the MC line has really finished playing; fail-safe cuts it so it cannot talk over the next beat."""
    yield Wait(until=eng.now() + eng.cfg.prompt_failsafe_ms, ready=lambda: not eng.token_live(token))
    if eng.token_live(token):
        eng.interrupt_mc("failsafe")


def run_gate(eng, g):
    yield eng.gate_wait(g)
    eng.close_gate(g)


def begin_question(eng, q, rnd=None, text_visible=True):
    eng.q = q
    eng.q_text_visible = text_visible
    eng.hint_level = 0
    eng.revealed_answer = None
    eng.question_no = q.number
    if rnd is not None:
        eng.round = rnd


def eligible(eng, rnd) -> bool:
    return any(s not in rnd.locked for s in eng.players)


def suspense(eng, q, prefix):
    eng.set_phase(f"{prefix}.suspense")
    eng.emit("answer.suspense", {"questionId": q.id})
    tok = eng.say("suspense", {"kind": q.kind})
    yield from say_wait(eng, tok)


def reveal(eng, q, results, prefix, credit=None):
    eng.set_phase(f"{prefix}.revealing_answer")
    eng.revealed_answer = q.answer
    names = [{"name": eng.players[r["seat"]].name, "correct": r["correct"]} for r in results]
    g = eng.open_gate(
        "answer.revealed",
        {"questionId": q.id, "answer": q.answer, "answerText": q.explanation, "results": results, "credit": credit},
        kind=q.kind,
        reaction=("react_answer", {"kind": q.kind, "answer": q.answer, "explanation": q.explanation, "results": names}),
    )
    yield from run_gate(eng, g)


def settle_and_show(eng, q, deltas, prefix, kind):
    eng.set_phase(f"{prefix}.settling")
    data = eng.settle(q, deltas)
    g = eng.open_gate("score.settled", data, kind=kind)
    yield from run_gate(eng, g)


# ---------------------------------------------------------------------------- the show
def game(eng):
    eng.set_phase("opening")
    g = eng.open_gate("show.opening", {"seats": eng.seats_wire(), "mode": eng.mode})
    yield from run_gate(eng, g)  # MC_READY: only now does the first greeting start
    tok = eng.say("greeting", {"names": eng.names(), "mode": eng.mode})
    yield from say_wait(eng, tok)
    yield from act_intro(eng, 1)
    for q in eng.content.act(1):
        yield from ox_question(eng, q)
    yield from act_intro(eng, 2)
    for q in eng.content.act(2):
        yield from (music_question(eng, q) if q.kind == "av" else buzzer_question(eng, q))
    yield from act_final(eng)


def act_intro(eng, act):
    eng.act = act
    eng.q = None
    eng.round = None
    eng.revealed_answer = None
    eng.hint_level = 0
    eng.set_phase("act_intro")
    assets = []
    if act == 2:
        t = eng.content.track
        assets = [{"assetId": t.asset_id, "mediaType": "audio", "bytes": t.bytes, "durationSec": t.duration_sec}]
    title = ACT_TITLES[act]
    g = eng.open_gate(
        "act.started",
        {"act": act, "title": title, "questionCount": len(eng.content.act(act)), "assets": assets},
        kind=str(act),
        reaction=("act_intro", {"act": act, "title": title, "names": eng.names()}),
    )
    yield from run_gate(eng, g)


# ---------------------------------------------------------------------------- act 1
def ox_question(eng, q):
    r = OxRound()
    begin_question(eng, q, r)
    eng.set_phase("ox.presenting")
    g = eng.open_gate(
        "question.presented", {"question": eng.public_question()}, kind="ox",
        reaction=("read_ox", {"number": q.number, "category": q.category, "text": q.text}),
    )
    yield from run_gate(eng, g)
    deadline = eng.now() + eng.cfg.ox_answer_ms
    eng.set_phase("ox.answering", deadline)
    yield Wait(until=deadline, ready=lambda: eng.all_connected_done(lambda s: s in r.picks))
    eng.input_deadline = None
    competitive = eng.mode == "competitive"
    picks = dict(r.picks)
    if picks:
        eng.set_phase("ox.revealing_choices")
        r.revealed = [{"seat": s, "choice": picks[s]} for s in sorted(picks)]
        g = eng.open_gate("ox.choices_revealed", {"choices": r.revealed})
        yield from run_gate(eng, g)
    unanimous = competitive and len(picks) == len(eng.players) and len(set(picks.values())) == 1
    eng.ox_streak = btr.next_streak(eng.ox_streak, unanimous, competitive)
    if unanimous:
        eng.emit("ox.unanimous", {"choice": next(iter(picks.values())), "streak": eng.ox_streak})
    if btr.should_offer(eng.ox_streak):
        eng.ox_streak = 0
        yield from betrayal_chance(eng, r)
    picks = dict(r.picks)  # a switch changes the effective pick
    yield from suspense(eng, q, "ox")
    results = [{"seat": s, "correct": picks.get(s) == q.answer} for s in sorted(eng.players)]
    yield from reveal(eng, q, results, "ox")
    deltas = {r_["seat"]: scoring.OX_POINTS for r_ in results if r_["correct"]}
    yield from settle_and_show(eng, q, deltas, "ox", "ox")


def betrayal_chance(eng, r):
    seat, selection, tied = btr.pick_target(eng.scores(), eng.rng)
    p = eng.players[seat]
    cur = r.picks[seat]
    b = BetrayalState(seat=seat, selection=selection, tied=tied, from_=cur)
    r.betrayal = b
    eng.set_phase("ox.betrayal")
    g = eng.open_gate(
        "betrayal.offered", {"seat": seat, "selection": selection, "currentChoice": cur, "tiedSeats": tied},
        reaction=("ask_reason", {"name": p.name, "choice": cur}),
    )
    yield from run_gate(eng, g)
    # reason: phone button or voice, 8 s
    eng.emit("betrayal.listening", {"seat": seat})
    b.status, b.step = "listening", "reason"
    dl = eng.now() + eng.cfg.betrayal_input_ms
    eng.input_deadline = dl
    b.listen_id = eng.listen(seat, "reason", 1, dl)
    yield Wait(until=dl, ready=lambda: b.reason is not None)
    eng.stop_listen(b.listen_id)
    b.listen_id, b.step = None, None
    # the MC offers the switch
    tok = eng.say("offer_switch", {"name": p.name, "choice": cur})
    yield from say_wait(eng, tok)
    # decision: phone or voice, 8 s; timeout keeps the pick
    b.step = "decision"
    dl = eng.now() + eng.cfg.betrayal_input_ms
    eng.input_deadline = dl
    b.listen_id = eng.listen(seat, "decision", 1, dl)
    yield Wait(until=dl, ready=lambda: b.decision is not None)
    eng.stop_listen(b.listen_id)
    b.listen_id, b.step = None, None
    eng.input_deadline = None
    switch = b.decision is True
    to = btr.flip(cur) if switch else cur
    if switch:
        r.picks[seat] = to
    b.to, b.status = to, "decided"
    g = eng.open_gate(
        "betrayal.decided", {"seat": seat, "from": cur, "to": to, "changed": switch},
        reaction=("react_betrayal", {"name": p.name, "changed": switch, "from": cur, "to": to, "reason": b.reason}),
    )
    yield from run_gate(eng, g)


# ---------------------------------------------------------------------------- act 2
def answer_phase(eng, q, rnd):
    """The holder answers (voice or phone), the engine judges once, a gate shows the verdict."""
    seat = rnd.holder
    p = eng.players[seat]
    if rnd.interrupt_pending:  # music: wait for media_ended(interrupted), at most 800 ms
        yield Wait(until=rnd.interrupted_at + eng.cfg.media_interrupt_wait_ms, ready=lambda: rnd.media_end is not None)
        rnd.interrupt_pending, rnd.clip, rnd.media_end = False, None, None
        eng.set_mic(True, "answer")
    deadline = eng.now() + eng.cfg.buzzer_answer_ms
    eng.set_phase("buzzer.answering", deadline)
    eng.begin_answer(rnd, seat, deadline)
    yield Wait(until=deadline, ready=lambda: rnd.answer is not None)
    heard = rnd.answer[0] if rnd.answer else ""
    eng.end_answer(rnd)
    correct = bool(heard) and answer_matches(heard, q.answer, q.aliases, q.kind)
    rnd.answer = None
    rnd.attempts.append((seat, correct))
    if correct:
        rnd.winner = seat
    else:
        rnd.locked = sorted(set(rnd.locked) | {seat})
    rnd.holder = None
    eng.set_phase("buzzer.judging")
    g = eng.open_gate(
        "buzzer.judged", {"seat": seat, "correct": correct, "lockedOut": list(rnd.locked)},
        reaction=("react_judge", {"name": p.name, "correct": correct}),
    )
    yield from run_gate(eng, g)


def finish_buzzer(eng, q, rnd):
    rnd.armed = False
    eng.set_mic(True, "round over")
    yield from suspense(eng, q, "buzzer")
    results = [{"seat": s, "correct": c} for s, c in rnd.attempts]
    credit = q.track.credit.to_wire() if q.kind == "av" and q.track else None
    yield from reveal(eng, q, results, "buzzer", credit)
    deltas = {rnd.winner: scoring.BUZZER_POINTS} if rnd.winner is not None else {}
    yield from settle_and_show(eng, q, deltas, "buzzer", "buzzer")


def buzzer_question(eng, q):
    rnd = BuzzRound()
    begin_question(eng, q, rnd, text_visible=False)
    eng.set_phase("buzzer.presenting")
    g = eng.open_gate("question.presented", {"question": eng.public_question()}, kind="buzzer")
    yield from run_gate(eng, g)
    eng.set_phase("buzzer.reading")
    rnd.armed = True
    eng.emit("buzzer.armed", {"questionId": q.id})
    resume = False
    while True:  # the reading, interrupted by buzzes
        tok = eng.say("read_buzzer", {"number": q.number, "category": q.category, "text": q.text, "resume": resume})
        rnd.reading_token = tok
        yield Wait(until=eng.now() + eng.cfg.reading_failsafe_ms,
                   ready=lambda tok=tok: rnd.holder is not None or not eng.token_live(tok))
        if rnd.holder is None:  # the reading finished playing (or the fail-safe hit)
            if eng.token_live(tok):
                eng.interrupt_mc("failsafe")
            break
        yield from answer_phase(eng, q, rnd)
        if rnd.winner is not None:
            break  # a correct early answer ends the reading; the unfinished text is never revealed
        resume = True
        rnd.armed = eligible(eng, rnd)
        eng.set_phase("buzzer.reading")
    rnd.reading_token = None
    if rnd.winner is None:
        eng.q_text_visible = True
        eng.emit("question.text_revealed", {"questionId": q.id, "text": q.text})
        while eligible(eng, rnd):
            dl = eng.now() + eng.cfg.buzzer_open_ms
            eng.set_phase("buzzer.open", dl)
            rnd.armed = True
            yield Wait(until=dl, ready=lambda: rnd.holder is not None)
            if rnd.holder is None:
                break  # nobody buzzed in time
            yield from answer_phase(eng, q, rnd)
            if rnd.winner is not None:
                break
    yield from finish_buzzer(eng, q, rnd)


def music_question(eng, q):
    track = q.track
    rnd = BuzzRound()
    begin_question(eng, q, rnd)
    eng.set_phase("buzzer.presenting")
    g = eng.open_gate(
        "question.presented", {"question": eng.public_question()}, kind="av",
        reaction=("intro_music", {"number": q.number, "category": q.category}),
    )
    yield from run_gate(eng, g)  # the introduction has finished playing before any music
    if eng.has_primary() and track.asset_id not in eng.media_ready:
        yield Wait(until=eng.now() + MEDIA_READY_WAIT_MS, ready=lambda: track.asset_id in eng.media_ready)
    max_level = len(track.clips) - 1
    level = 0
    while True:
        start, end = track.clips[level]
        rnd.level, eng.hint_level = level, level
        eng.set_phase("buzzer.media")
        rnd.armed = True
        eng.emit("buzzer.armed", {"questionId": q.id})
        eng.set_mic(False, "media")  # the MC is idle and the mic closed until the clip is over
        rnd.clip, rnd.media_end, rnd.media_playing, rnd.interrupt_pending = (level, start, end), None, True, False
        eng.emit("av.play", {"assetId": track.asset_id, "level": level, "startSec": start, "endSec": end})
        watchdog = eng.now() + int(round((end - start) * 1000)) + eng.cfg.media_watchdog_extra_ms
        yield Wait(until=watchdog, ready=lambda: rnd.holder is not None or rnd.media_end is not None)
        if rnd.holder is None:  # natural end, stage error, or watchdog
            rnd.media_playing, rnd.clip, rnd.media_end = False, None, None
            eng.set_mic(True, "media ended")
        while True:  # buzz window(s) at this level
            if rnd.holder is None:
                dl = eng.now() + eng.cfg.music_open_ms
                eng.set_phase("buzzer.open", dl)
                rnd.armed = True
                yield Wait(until=dl, ready=lambda: rnd.holder is not None)
                if rnd.holder is None:
                    break
            yield from answer_phase(eng, q, rnd)
            if rnd.winner is not None or not eligible(eng, rnd):
                break
        if rnd.winner is not None or level >= max_level:
            break
        level += 1  # hint: reset eligibility, MC clue, longer clip
        rnd.locked, rnd.armed = [], False
        eng.hint_level = level
        eng.set_phase("buzzer.hint")
        g = eng.open_gate(
            "av.hint", {"level": level, "media": {"assetId": track.asset_id, "mediaType": "audio"}},
            reaction=("hint_line", {"level": level, "max_level": max_level, "clue": track.clues[level - 1]}),
        )
        yield from run_gate(eng, g)
    yield from finish_buzzer(eng, q, rnd)


# ---------------------------------------------------------------------------- act 3 and finale
def standings(eng):
    ranks = eng.ranks()
    win = set(scoring.winners(eng.scores()))
    rows = [{"seat": s, "playerId": p.id, "name": p.name, "fanType": p.fan, "score": p.score,
             "rank": ranks[s], "winner": s in win} for s, p in eng.players.items()]
    return sorted(rows, key=lambda r: (r["rank"], r["seat"]))


def act_final(eng):
    q = eng.content.act(3)[0]
    yield from act_intro(eng, 3)
    r = FinalRound()
    eng.round = r
    eng.set_phase("final.intro")
    tok = eng.say("final_intro", {"scores": [{"name": p.name, "score": p.score} for _, p in sorted(eng.players.items())]})
    yield from say_wait(eng, tok)
    eng.set_phase("final.category")
    r.category = q.category
    g = eng.open_gate("final.category", {"category": q.category})
    yield from run_gate(eng, g)
    # secret bets
    dl = eng.now() + eng.cfg.final_bet_ms
    eng.set_phase("final.betting", dl)
    yield Wait(until=dl, ready=lambda: eng.all_connected_done(lambda s: s in r.bet_placed))
    for s in eng.players:
        r.bets.setdefault(s, 0)  # a missing bet is 0
    eng.input_deadline = None
    eng.emit("final.bets_locked", {})
    pre = eng.scores()
    # the question appears and is read
    begin_question(eng, q)
    eng.set_phase("final.question")
    g = eng.open_gate(
        "question.presented", {"question": eng.public_question()}, kind="final",
        reaction=("read_final", {"number": q.number, "category": q.category, "text": q.text, "choices": list(q.choices)}),
    )
    yield from run_gate(eng, g)
    dl = eng.now() + eng.cfg.final_answer_ms
    eng.set_phase("final.answering", dl)
    yield Wait(until=dl, ready=lambda: eng.all_connected_done(lambda s: s in r.answer_placed))
    eng.input_deadline = None
    eng.emit("final.answers_locked", {})
    eng.set_phase("final.revealing_choices")
    r.revealed_choices = [{"seat": s, "choice": r.choices.get(s)} for s in sorted(eng.players)]
    g = eng.open_gate("final.choices_revealed", {"choices": r.revealed_choices})
    yield from run_gate(eng, g)
    eng.set_phase("final.revealing_bets")
    r.revealed_bets = []
    for s in scoring.bet_reveal_order(pre):
        bet = r.bets[s]
        all_in = scoring.is_all_in(bet, pre[s])
        r.revealed_bets.append({"seat": s, "bet": bet, "allIn": all_in})
        g = eng.open_gate("final.bet_revealed", {"seat": s, "bet": bet, "allIn": all_in, "remaining": pre[s] - bet})
        yield from run_gate(eng, g)
    yield from suspense(eng, q, "final")
    results = [{"seat": s, "correct": r.choices.get(s) == q.answer} for s in sorted(eng.players)]
    yield from reveal(eng, q, results, "final")
    deltas = {x["seat"]: scoring.final_delta(r.bets[x["seat"]], x["correct"]) for x in results}
    yield from settle_and_show(eng, q, deltas, "final", "final")
    # finale
    rows = standings(eng)
    winners = scoring.winners(eng.scores())
    tie = len(winners) > 1
    eng.set_phase("finale.winner")
    g = eng.open_gate(
        "finale.winner",
        {"winners": winners, "tie": tie,
         "finalScores": [{"seat": x["seat"], "delta": 0, "score": x["score"], "rank": x["rank"]} for x in rows]},
        reaction=("react_winner", {"winners": [eng.players[s].name for s in winners], "tie": tie,
                                   "standings": [{"name": x["name"], "score": x["score"], "rank": x["rank"]} for x in rows]}),
    )
    yield from run_gate(eng, g)
    eng.set_phase("finale.curtain")
    g = eng.open_gate(
        "finale.results", {"mode": eng.mode, "winners": winners, "tie": tie, "standings": rows},
        reaction=("farewell", {"mode": eng.mode,
                               "standings": [{"name": x["name"], "score": x["score"], "rank": x["rank"]} for x in rows]}),
    )
    yield from run_gate(eng, g)
    eng.set_phase("ended")
    eng.emit("game.ended", {})
