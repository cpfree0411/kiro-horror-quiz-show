"""Deliberate real-API helpers (free tier). Never run by tests or CI. Every run opens ONE real Live session.

  speech <word> <out.wav>   have the Live model say a word, save it as a 16 kHz WAV for Chromium's fake microphone
  game   <mic.wav> <dir>    play a full solo game in headless Chromium against the live MC; writes evidence into <dir>
  hint   <dir>              solo game up to the music question, then ONE scripted hint request (typed to the model as what the
                            player said; the mic is not used), no loops: does the live MC speak clue 1? Writes <dir>/hint_report.json

Sessions are appended (time and purpose only) to $KHQS_LIVE_LOG, default <dir>/live_sessions.log.
"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "server"), str(REPO / "tests"), str(REPO / "tests" / "e2e"), str(REPO / "tests" / "server")]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/srv/workdata/browser-cache/ms-playwright")

from khqs.mc.transport import AudioOut, Closed, GeminiTransport, LiveError, TurnComplete  # noqa: E402
from khqs.server.settings import Settings  # noqa: E402


async def speech(word: str, out: Path) -> None:
    s = Settings()
    log = Path(os.environ.get("KHQS_LIVE_LOG", out.parent / "live_sessions.log"))
    tr = GeminiTransport(s.env_file, s.live_model, s.live_voice, log, "speech-fixture")
    await tr.connect("You are a plain text-to-speech voice. Say exactly the requested word, clearly, and nothing else.", None)
    pcm = bytearray()
    try:
        await tr.send_turn(f"Say only this single word, clearly: {word}")
        async def collect():
            async for ev in tr.events():
                if isinstance(ev, AudioOut):
                    pcm.extend(ev.pcm)
                elif isinstance(ev, (TurnComplete, Closed)):
                    return
        await asyncio.wait_for(collect(), 40)
    finally:
        await tr.close()
    raw = out.with_suffix(".raw")
    raw.write_bytes(bytes(pcm))
    subprocess.run(["sox", "-t", "raw", "-r", "24000", "-e", "signed", "-b", "16", "-c", "1", str(raw), "-r", "16000", str(out), "pad", "0", "4"], check=True)
    raw.unlink()
    print(f"saved {out} ({len(pcm) / 48000:.2f} s of speech)")


async def hint(out: Path, factory=None) -> None:
    """One real Live session. Solo, dev bank. The player's words reach the model as a client turn, so the model itself makes the
    report_answer call (the race this checks is around that tool turn); the engine and the adapter are the real ones."""
    import json
    import logging
    import random

    import live_rig
    from khqs.engine.config import EngineConfig
    from khqs.engine.core import Engine
    from khqs.engine.effects import McSay

    out.mkdir(parents=True, exist_ok=True)
    logfile = out / "hint_smoke.log"
    h = logging.FileHandler(logfile, mode="w")
    h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    logging.getLogger("khqs").addHandler(h)
    logging.getLogger("khqs").setLevel(logging.INFO)

    def real_engine(self):  # real windows instead of the rig's tiny ones
        cfg = EngineConfig(buzzer_answer_ms=60_000)
        return Engine(self.bank, self.clock, random.Random(3), cfg, game_index=self.game_index, **self.mc.engine_flags())
    live_rig.RigHost._new_engine = real_engine
    rig = live_rig.Rig(live_log=out / "live_sessions.log", join_grace_s=3600.0)  # no phone socket joins in this check
    s = rig.host.settings
    rig.mc.factory = factory or (lambda: GeminiTransport(s.env_file, s.live_model, s.live_voice, s.live_log, "hint-smoke"))
    report: dict = {"ok": False}
    await rig.up()  # opens the one real session
    try:
        rig.host.join("Mina")
        rig.host.start()
        eng = rig.eng
        track = eng.content.track
        for _ in range(3):
            await rig.until(lambda: eng.phase == "ox.answering", timeout=120)
            rig.host.run(eng.phone_action, 1, {"type": "ox", "choice": "O"})
            await rig.until(lambda: eng.phase != "ox.answering", timeout=30)
        await rig.until(lambda: eng.q is not None and eng.q.kind == "av" and eng.phase.startswith("buzzer"), timeout=300)
        rig.host.run(eng.stage_message, "c1", {"type": "stage.media_ready", "data": {"assetIds": [track.asset_id]}})
        await rig.until(lambda: eng.phase == "buzzer.media" and eng.round.armed, timeout=60)
        assert rig.host.run(eng.phone_action, 1, {"type": "buzz"}).ok
        await rig.until(lambda: rig.mc.listen is not None and rig.mc.listen.purpose == "answer", timeout=60)
        await asyncio.sleep(1.0)
        rig.mc.listen.meter.voiced_ms = 1000.0  # voiced evidence: there is no microphone in this check
        t0 = len(eng.stream)
        await rig.mc.transport.send_turn('The player Mina just said aloud: "It\'s too hard, give me a hint!"')
        report["request_sent"] = True
        await rig.until(lambda: any(isinstance(e, McSay) and e.cue == "hint_grant" for _, e, _ in rig.host.recorder.mc_fx), timeout=60)
        await rig.until(lambda: eng.phase == "buzzer.answering" and rig.mc.listen is not None and rig.mc.listen.purpose == "answer"
                        and eng.round.hints_given == 1, timeout=60)
        grant = next(e for _, e, _ in rig.host.recorder.mc_fx if isinstance(e, McSay) and e.cue == "hint_grant")
        lines = [l for l in logfile.read_text().splitlines() if "mc cue" in l or "mc tool" in l or "mc turn_complete" in l or "mc empty" in l]
        done = [l for l in lines if "mc cue done cue=hint_grant" in l]
        report.update(ok=True, sessions_opened=rig.mc.sessions_opened, grant_facts={k: v for k, v in grant.facts.items() if k != "name"},
                      log_lines=lines, captions_after_request=[m["data"]["text"] for m in eng.stream[t0:] if m["type"] == "mc.caption"],
                      grant_audio_log=done, clue_1=track.clues[0], hints_given=eng.round.hints_given)
    except Exception as e:  # noqa: BLE001
        report["error"] = f"{type(e).__name__}: {e}"
        report["log_lines"] = [l for l in logfile.read_text().splitlines() if l.split(" ", 3)[-1].startswith("mc ")][-40:]
    finally:
        await rig.down()
    (out / "hint_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "speech":
        asyncio.run(speech(sys.argv[2], Path(sys.argv[3])))
    elif mode == "hint":
        asyncio.run(hint(Path(sys.argv[2])))
    elif mode == "game":
        from live_smoke_game import main  # noqa: E402
        main(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(__doc__)
