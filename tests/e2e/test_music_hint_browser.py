"""P7 acceptance: one full game on the real stage with the mock MC, where two players ask for a hint in the music
question through the HINT button of the phone UI. The first is refused (a NO), the second is granted (AGREE).

Slow (minutes of real time). Run it alone:
    KHQS_EVIDENCE_DIR=/srv/workdata/build-cache/khqs-evidence/p7 scripts/test.sh -m slow tests/e2e/test_music_hint_browser.py
"""
import pytest
from playwright.sync_api import sync_playwright

from khqs.engine.effects import McSay
from khqs.server.runner import RunningServer
from khqs.server.settings import Settings
from support.secrecy import assert_no_leaks
from driver import Show
from server_helpers import free_port

pytestmark = pytest.mark.slow

ANSWERS = {4: "Mirror", 5: "Danse Macabre", 6: "Pumpkin", 7: "Broomstick"}  # dev set A
MUSIC = 5


class _Merged:
    def __init__(self, rec, extra_snaps):
        self.eng, self.stream, self.views, self.mc_fx, self.directs = rec.eng, rec.stream, rec.views, rec.mc_fx, rec.directs
        self.snapshots = list(rec.snapshots) + list(extra_snaps)


def test_hint_button_and_agree_no_buttons_in_a_full_game_with_the_mock_mc():
    s = Settings(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True,
                 record=True, seed=12, mock_speed=2.0, join_grace_s=30.0).validate()
    srv = RunningServer(s).start()
    try:
        with sync_playwright() as pw:
            show = Show(pw, srv, "hints")
            try:
                show.open_stage()
                names = ["Mina", "Junho", "Ray"]
                show.join_pad(names[0])
                show.join_phone(names[1])
                show.join_phone(names[2])
                seats = sorted(p.seat for p in show.players)
                first, last = seats[0], seats[-1]
                show.start_show()
                eng = srv.host.engine
                actions: list = []
                real_action = eng.phone_action

                def spy(seat, action):  # kept for the failure message: every phone action and what the engine said
                    res = real_action(seat, action)
                    if eng.q is not None and eng.q.kind == "av":
                        actions.append((seat, action.get("type"), action.get("text") or action.get("agree"), res.ok, res.error, eng.phase))
                    return res
                eng.phone_action = spy
                seen_screens: dict[str, set] = {}
                board: list[str] = []
                plan = {
                    "ox": lambda seat, qn: "O",
                    # the music question: the first player buzzes and asks (refused), then answers wrong; the last asks (granted), then is right
                    "buzz": lambda qn, attempts, phase: (first if attempts == 0 else last) if qn in ANSWERS and attempts <= 1 else None,
                    "text": lambda qn, seat, attempts: "nope" if (attempts == 0 and qn in ANSWERS) else eng.q.answer,  # the music track depends on the seed and the joins
                    "bet": lambda seat, score: score // 2,
                    "final": lambda seat: "B",
                    "hint": lambda qn, seat, attempts: qn == MUSIC,
                    "vote": lambda qn, voter, attempts: not (attempts == 0 and voter == last),  # the first ask is refused by `last`
                }
                orig = show.tick

                def tick(pl):
                    orig(pl)
                    for p in show.players:
                        v = p.view()
                        if v:
                            seen_screens.setdefault(p.name, set()).add(v["screen"])
                    if eng.phase == "buzzer.hint" and len(board) < 40:
                        board.append(show.stage.evaluate(
                            "[...document.querySelectorAll('*')].filter(e => e.children.length === 0 && /HINT!/.test(e.textContent)).length"))
                show.tick = tick
                show.play(plan)
                show.finale_checks()

                assert eng.phase == "ended" and eng.stats["gate_timeouts"] == 0 and show.errors == [], show.errors
                cue_list = [(e.cue, e.facts) for _, e, _ in srv.host.recorder.mc_fx if isinstance(e, McSay)]
                track = eng.content.track
                asks = [f for c, f in cue_list if c == "hint_ask"]
                assert [f["name"] for f in asks] == [eng.players[first].name, eng.players[last].name]
                assert [c for c, _ in cue_list if c == "hint_refused"] == ["hint_refused"]
                grants = [f for c, f in cue_list if c == "hint_grant"]
                assert grants == [{"name": eng.players[last].name, "how": "agreed", "kind": "clue", "text": track.clues[0], "number": 1}]
                # the music question: first asked, refused, wrong; last asked, granted, right (+20)
                qid = next(q.id for q in eng.content.questions if q.kind == "av")
                start = next(m["sseq"] for m in eng.stream if m["type"] == "question.presented" and m["data"]["question"]["id"] == qid)
                rev = next(m for m in eng.stream if m["type"] == "answer.revealed" and m["data"]["questionId"] == qid)
                judged = [m["data"] for m in eng.stream if m["type"] == "buzzer.judged" and start < m["sseq"] < rev["sseq"]]
                import os
                with open(os.path.join(os.environ.get("KHQS_EVIDENCE_DIR", "/tmp"), "hint_actions.txt"), "w") as f:
                    f.write("\n".join(map(repr, actions)))
                assert [(j["seat"], j["correct"]) for j in judged] == [(first, False), (last, True)], "see hint_actions.txt"
                settled = next(m for m in eng.stream if m["type"] == "score.settled" and m["sseq"] > rev["sseq"])["data"]["deltas"]
                assert {d["seat"]: d["delta"] for d in settled} == {first: 0, **{s_: 0 for s_ in seats}, last: 20}
                hint_phases = [m for m in eng.stream if m["type"] == "phase.changed" and m["data"]["phase"] == "buzzer.hint" and start < m["sseq"] < rev["sseq"]]
                assert len(hint_phases) == 2  # one per request, none from the ladder (it has its own av.hint gate)
                # phone screens: the requester waited, the voters saw AGREE / NO and then the locked vote
                voters = set().union(*[seen_screens[n] for n in names], *[set(p.log) for p in show.players])
                assert {"hint_vote", "hint_wait"} <= voters, voters  # (hint_voted lasts less than one poll when the next vote closes the window)
                # the stage showed its HINT! board while the MC asked and gave the hint
                assert board and max(board) >= 1, board
                # nothing new on the wire, nothing secret on any channel
                assert {m["type"] for m in eng.stream if m["type"].startswith(("buzzer.", "hint"))} <= {
                    "buzzer.armed", "buzzer.pressed", "buzzer.judged"}
                caps = " ".join(m["data"]["text"] for m in eng.stream if m["type"] == "mc.caption")
                assert track.clues[0] in caps and track.composer not in caps
                rec = srv.host.recorder
                stage_snaps = [m for who, m in show.frames if who == "stage:stage" and m["type"] == "snapshot"]
                assert_no_leaks(_Merged(rec, stage_snaps))
                show.shot("podium_after_hints")
            finally:
                show.close()
    finally:
        srv.stop()
