"""P2 acceptance: full games on the real stage through the real server, driven in headless Chromium.

Slow (minutes of real time: the stage's animations set the pace). Run one game at a time, or in parallel processes:
    scripts/test.sh -m slow tests/e2e/test_live_games.py -k players1
"""
import json
import os

import pytest
from playwright.sync_api import sync_playwright

from khqs.server.runner import RunningServer
from khqs.server.settings import Settings
from support.secrecy import assert_no_leaks
from driver import Show
from server_helpers import free_port

pytestmark = pytest.mark.slow

ANSWERS = {4: "Mirror", 5: "Danse Macabre", 6: "Pumpkin", 7: "Broomstick"}  # dev set A (seed makes game 0 use set A)


def settings(seed):
    return Settings(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True,
                    record=True, seed=seed, mock_speed=2.0, join_grace_s=30.0).validate()


def plan_for(seats):
    first, last = seats[0], seats[-1]
    solo = len(seats) == 1

    def buzz(qn, attempts, phase):
        if qn in ANSWERS:
            if solo or attempts == 1:
                return last
            if attempts == 0:
                return first
        return None

    def text(qn, seat, attempts):
        wrong = (not solo) and attempts == 0
        return "nope" if wrong else ANSWERS[qn]

    return {
        "ox": lambda seat, qn: "O",  # unanimous O on Q1 and Q2 triggers the betrayal chance when 2+ play
        "buzz": buzz, "text": text,
        "bet": lambda seat, score: score if seat == last else score // 2,
        "final": lambda seat: "B" if seat != first or solo else "A",
    }


@pytest.mark.parametrize("n_pad,n_phone,tag", [(1, 0, "players1"), (1, 1, "players2"), (1, 2, "players3")])
def test_full_game_in_a_browser(n_pad, n_phone, tag):
    srv = RunningServer(settings({"players1": 11, "players2": 12, "players3": 13}[tag])).start()
    try:
        with sync_playwright() as pw:
            show = Show(pw, srv, tag)
            try:
                show.open_stage()
                names = ["Mina", "Junho", "Ray"][: n_pad + n_phone]
                show.join_pad(names[0])
                for n in names[1:]:
                    show.join_phone(n)
                seats = sorted(p.seat for p in show.players)
                assert seats == sorted({1: [1], 2: [0, 1], 3: [0, 1, 2]}[len(names)])
                label = show.stage.locator("#khqs-pad .lbl").inner_text()
                assert "visible to everyone" in label
                show.start_show()
                reload_target = next((p for p in show.players if p.kind == "phone"), show.players[0])
                show.play(plan_for(seats), reload_at=lambda e: reload_target if (e.q and e.q.number >= 5) else None)
                ev = show.finale_checks()
                eng = srv.host.engine

                # --- J1: completes, stage primary and acking, no page errors
                assert eng.phase == "ended" and eng.stream[-1]["type"] == "game.ended"
                assert len([m for m in eng.stream if m["type"] == "score.settled"]) == 8
                assert eng.stats["gate_timeouts"] == 0, "every gate must be closed by the stage's ack"
                assert {s["live"]["role"] for s in show.samples} == {"primary"}
                assert show.errors == [], show.errors
                assert reload_target.reloaded and all(pl.connected for pl in eng.players.values())
                if len(names) > 1:
                    assert [m for m in eng.stream if m["type"] == "betrayal.offered"], "betrayal chance never happened"
                # --- J4: podium and NEW SHOW
                assert ev["pods"] >= 1 and ev["saw_new_show"] and not ev["early_new_show"]
                # --- J2: secrecy over everything the browsers actually received
                rec = srv.host.recorder
                stage_frames = [m for who, m in show.frames if who == "stage:stage"]
                assert any(m["type"] == "show.opening" for m in stage_frames)
                for m in stage_frames:
                    if m["type"] not in ("snapshot", "pong", "error"):
                        assert m == eng.stream[m["sseq"] - 1], f"the stage received something the engine did not record: #{m['sseq']}"
                snaps = [m for m in stage_frames if m["type"] == "snapshot"]
                assert snaps, "the stage never received a snapshot"
                assert_no_leaks(_Merged(rec, snaps))
                _phone_frames_are_private(show)
                show.new_show()
                for p in show.players:
                    if p.kind == "phone":
                        p.page.wait_for_function("document.getElementById('pc-main').dataset.screen === 'invalid'", timeout=10000)
            finally:
                show.close()
    finally:
        srv.stop()


class _Merged:
    """The recorder plus the snapshots the browser actually received, for the secrecy scanner."""
    def __init__(self, rec, extra_snaps):
        self.eng, self.stream, self.views, self.mc_fx, self.directs = rec.eng, rec.stream, rec.views, rec.mc_fx, rec.directs
        self.snapshots = list(rec.snapshots) + list(extra_snaps)


def _phone_frames_are_private(show):
    """Each phone socket only ever received views of its own player, with only own-entry fields."""
    seen = 0
    for who, m in show.frames:
        if m.get("type") != "view" or not who.endswith(":phone"):
            continue
        seen += 1
        v = m["view"]
        assert set(v["own"]) <= {"pick", "canBuzz", "textBox", "betrayal", "maxBet", "bet", "choice"}, v["own"]
        if who.startswith("phone-"):
            assert v["you"]["name"] == who.split(":")[0][len("phone-"):], (who, v["you"])
    assert seen > 20
