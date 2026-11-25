"""Scenario themes 4 and 5: trio final with an all-in and a comeback, and a stage reconnect mid bet reveal."""
import json

from support import scenarios as sc
from support.bots import Bots
from support.content_fixture import BANK
from support.flows import final_sim
from support.harness import new_sim

KEYS = {
    "act.started": ["act", "title", "questionCount"], "final.category": ["category"],
    "question.presented": ["question"], "final.choices_revealed": ["choices"],
    "final.bet_revealed": ["seat", "bet", "allIn", "remaining"],
    "answer.revealed": ["questionId", "answer", "answerText", "results", "credit"],
    "score.settled": ["deltas", "leadChange"], "finale.winner": ["winners", "tie", "finalScores"],
}


def _act3(sim):
    first = next(i for i, m in enumerate(sim.stream) if m["type"] == "act.started" and m["data"]["act"] == 3)
    return sim.stream[first:]


def test_final_allin_matches_scenario():
    sim = final_sim()
    sim.until_ended()
    scn = sc.load("trio-act3-final-allin")
    w = next(i for i, m in enumerate(scn) if m["type"] == "finale.winner")
    e = next(i for i, m in enumerate(_act3(sim)) if m["type"] == "finale.winner")
    diffs = sc.compare(
        _act3(sim)[: e + 1], scn[: w + 1], ignore=("mc.status", "snapshot"), keys=KEYS,
        # intended divergence: an acknowledged suspense step phase is not in the scenario's answer.suspense -> same, no skip needed
    )
    assert diffs == [], diffs
    # rev 1.1 tail: curtain, results gate, ended, game.ended
    tail = [(m["type"], m["data"].get("phase")) for m in _act3(sim)[e + 1:] if m["type"] != "mc.status"]
    assert tail == [("phase.changed", "finale.curtain"), ("finale.results", None), ("phase.changed", "ended"), ("game.ended", None)]
    assert sim.stream[-1]["type"] == "game.ended"
    res = sim.of("finale.results")[0]
    assert res["data"]["standings"] == [
        {"seat": 0, "playerId": "p-1", "name": "Mina", "fanType": sim.eng.players[0].fan, "score": 220, "rank": 1, "winner": True},
        {"seat": 2, "playerId": "p-3", "name": "Ray", "fanType": sim.eng.players[2].fan, "score": 160, "rank": 2, "winner": False},
        {"seat": 1, "playerId": "p-2", "name": "Junho", "fanType": sim.eng.players[1].fan, "score": 80, "rank": 3, "winner": False},
    ]
    assert res["data"]["mode"] == "competitive" and res["data"]["tie"] is False


def test_bets_reveal_lowest_first_leader_last_and_stream_stops_after_ended():
    sim = final_sim()
    sim.until_ended()
    assert [m["data"]["seat"] for m in sim.of("final.bet_revealed")] == [2, 0, 1]
    n = len(sim.stream)
    sim.run(120_000)
    assert len(sim.stream) == n and sim.eng.next_due() is None


def test_no_question_text_or_choices_while_betting_and_bets_hidden_until_revealed():
    sim = final_sim(bets={0: 97, 1: 113, 2: 80})
    sim.until_ended()
    q = BANK.sets[0].final
    first_present = next(m for m in sim.stream if m["type"] == "question.presented" and m["data"]["question"]["kind"] == "final")
    lock = next(m for m in sim.stream if m["type"] == "final.bets_locked")
    for snap in sim.snapshots:
        if snap["sseq"] < first_present["sseq"] and snap["data"]["game"]["act"] == 3:
            blob = json.dumps(snap, ensure_ascii=False)
            assert q.text not in blob and q.choices[0] not in blob
            assert snap["data"]["question"] is None
    reveal_seq = {m["data"]["seat"]: m["sseq"] for m in sim.of("final.bet_revealed")}
    import re
    for m in sim.stream:
        blob = json.dumps(m["data"])
        for seat, amount in ((0, 97), (1, 113)):
            if m["sseq"] < reveal_seq[seat]:
                assert not re.search(rf"(?<![\w.-]){amount}(?![\w.-])", blob), (m["type"], amount)
    for snap in sim.snapshots:
        blob = json.dumps(snap["data"])
        for seat, amount in ((0, 97), (1, 113)):
            if snap["sseq"] < reveal_seq[seat]:
                assert not re.search(rf"(?<![\w.-]){amount}(?![\w.-])", blob), (snap["sseq"], amount)
    for snap in sim.snapshots:
        revealed = {b["seat"] for b in (snap["data"]["round"] or {}).get("revealedBets") or []} if snap["data"]["round"] else set()
        assert all(reveal_seq[s] <= snap["sseq"] for s in revealed)
    assert lock["sseq"] < first_present["sseq"]


def test_reconnect_mid_bet_reveal_snapshot_open_gate_and_skipped_ack():
    sim = final_sim(bets={0: 97, 1: 113, 2: 80})
    sim.ack_filter = lambda m: not (m["type"] == "final.bet_revealed" and m["data"]["seat"] == 2)  # the stage "drops"
    sim.until_type("final.bet_revealed")
    sim.eng.phone_connection(2, False)  # Ray's phone is gone too (after he played)
    sim.pump()
    gate_msg = sim.of("final.bet_revealed")[0]
    sim.eng.stage_disconnect(sim.conn)
    sim.pump()
    role = sim.hello(conn="stage-2", role="primary", last=gate_msg["sseq"])
    assert role == "primary"
    snap = sim.directs[-1][1]
    assert snap["type"] == "snapshot" and snap["sseq"] == sim.stream[-1]["sseq"]  # the last stream position; it consumes no number
    d = snap["data"]
    assert d["game"]["phase"] == "final.revealing_bets"
    assert d["openGate"] == {"id": gate_msg["gate"]["id"], "type": "final.bet_revealed"}
    r = d["round"]
    assert r["kind"] == "final" and r["betPlaced"] == [0, 1, 2] and r["answerPlaced"] == [0, 1, 2]
    assert r["revealedChoices"] == [{"seat": 0, "choice": "B"}, {"seat": 1, "choice": "A"}, {"seat": 2, "choice": "B"}]
    assert r["revealedBets"] == [{"seat": 2, "bet": 80, "allIn": True}]  # only the one already revealed
    assert d["seats"][2]["player"]["connected"] is False
    assert "97" not in json.dumps(d) and "113" not in json.dumps(d)
    # the rebuilt stage draws the rest pose and acks with skipped=true; play continues contiguously
    sim.ack_filter = None
    n = len(sim.stream)
    sim.stage_send("stage.beat_done", {"gate": gate_msg["gate"]["id"], "sseq": gate_msg["sseq"], "skipped": True}, conn="stage-2")
    sim.until_type("final.bet_revealed", 2)
    assert sim.stream[n]["sseq"] == sim.stream[n - 1]["sseq"] + 1
    assert [m["sseq"] for m in sim.stream] == list(range(1, len(sim.stream) + 1))  # no gaps ever
    assert sim.of("final.bet_revealed")[1]["data"]["seat"] == 0
