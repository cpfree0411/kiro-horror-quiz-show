"""Deliberate real-API helpers (free tier). Never run by tests or CI. Every run opens ONE real Live session.

  speech <word> <out.wav>   have the Live model say a word, save it as a 16 kHz WAV for Chromium's fake microphone
  game   <mic.wav> <dir>    play a full solo game in headless Chromium against the live MC; writes evidence into <dir>

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


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "speech":
        asyncio.run(speech(sys.argv[2], Path(sys.argv[3])))
    elif mode == "game":
        from live_smoke_game import main  # noqa: E402
        main(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(__doc__)
