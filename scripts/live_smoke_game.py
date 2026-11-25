"""One real, deliberate end-to-end run: solo game, real Gemini Live MC, headless Chromium, fake microphone from a WAV.
Opens exactly one real Live session (counted in live_sessions.log). Not used by tests."""
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from khqs.server.runner import RunningServer
from khqs.server.settings import Settings
from driver import Show
from server_helpers import free_port


def main(wav: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    os.environ["KHQS_EVIDENCE_DIR"] = str(out)
    import driver
    driver.EVIDENCE = str(out)
    s = Settings(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True, record=True, seed=5,
                 mc="live", buzzer_answer_ms=60_000, join_grace_s=120.0, live_log=out / "live_sessions.log").validate()
    srv = RunningServer(s).start()
    host = srv.host
    report = {"ok": False}
    try:
        with sync_playwright() as pw:
            show = Show(pw, srv, "smoke", extra_args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                                     f"--use-file-for-fake-audio-capture={wav}"])
            try:
                heard_log = []
                show.open_stage()
                show.join_pad("Mina")
                show.start_show()
                eng0 = host.engine
                orig_va = eng0.mc_voice_answer

                def va(listen_id, heard, recognition, voiced):
                    ok = orig_va(listen_id, heard, recognition, voiced)
                    heard_log.append({"q": eng0.question_no, "heard": heard, "recognition": recognition, "voiced": voiced, "accepted": ok})  # evidence only
                    return ok
                eng0.mc_voice_answer = va
                show.stage.wait_for_function("document.querySelector('#khqs-chip').dataset.mc === 'online'", timeout=60000)
                report["connected"] = True
                typed = set()
                orig = show.tick

                def tick(plan):
                    orig(plan)
                    v = show.players[0].view()
                    qn = host.engine.question_no
                    if v and v["screen"] == "answer_voice" and qn in (6, 7) and qn not in typed:
                        typed.add(qn)
                        show.players[0].target.click("#type-instead")
                show.tick = tick
                plan = {"ox": lambda seat, qn: "O", "buzz": lambda qn, attempts, phase: 1 if qn in (4, 5, 6, 7) and attempts == 0 else None,
                        "text": lambda qn, seat, attempts: {6: "Pumpkin", 7: "Broomstick"}.get(qn, "Mirror"), "bet": lambda seat, score: score // 2,
                        "final": lambda seat: "B"}
                t0 = time.monotonic()
                show.play(plan, timeout=1500)
                report["game_seconds"] = round(time.monotonic() - t0)
                ev = show.finale_checks()
                eng = host.engine
                mc = host.mc
                judged = [{"q": None, "correct": m["data"]["correct"]} for m in eng.stream if m["type"] == "buzzer.judged"]
                report.update(
                    ok=eng.phase == "ended", phase=eng.phase, mc_state=mc.state, mc_reason=mc.reason, sessions_opened=mc.sessions_opened,
                    gate_timeouts=eng.stats["gate_timeouts"], page_errors=show.errors, judged=judged,
                    captions=[m["data"]["text"] for m in eng.stream if m["type"] == "mc.caption"][:12],
                    voice_failures_asked_again=sum(1 for _, e, _ in host.recorder.mc_fx if getattr(e, "cue", "") == "ask_again"),
                    mc_status_changes=len([m for m in eng.stream if m["type"] == "mc.status"]),
                    mic_frames_forwarded=show.stage.evaluate("KHQS_MC.forwarded"), podium=ev,
                    heard=heard_log, lines_played=len(show.stage.evaluate("KHQS_MC.played")), lines_started=len(show.stage.evaluate("KHQS_MC.started")),
                )
                (out / "smoke_prompts_sent.txt").write_text("\n".join(mc.sent_turns), encoding="utf-8")
                from support.secrecy import assert_no_leaks
                from khqs.engine.effects import McSay
                rec = host.recorder
                rec.mc_fx = list(rec.mc_fx) + [(pos, McSay("p", "x", {"prompt": t}), 0) for pos, t in zip(mc.sent_sseq, mc.sent_turns)]
                try:
                    assert_no_leaks(rec)
                    report["secrecy_scan"] = "clean"
                except AssertionError as e:
                    report["secrecy_scan"] = "LEAK: " + str(e)[:300]
            finally:
                show.close()
    finally:
        srv.stop()
    (out / "smoke_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
