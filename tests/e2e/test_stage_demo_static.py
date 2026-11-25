"""P0 acceptance: stage/index.html#demo plays statically (no server code of ours involved).

Slow (about 5 minutes, real time). Run:  scripts/test.sh -m slow tests/e2e/test_stage_demo_static.py
Needs internet for the Google Fonts the stage links to (the stage works without them but looks different).
Screenshots go to $KHQS_EVIDENCE_DIR (default /srv/workdata/build-cache/khqs-evidence/p0), outside the repo.
"""
import functools
import http.server
import os
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

DEMO_TIMEOUT_S = 360
SHOT_TIMES_S = (20, 60, 120, 180, 240)


def _serve(directory: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(Quiet, directory=str(directory))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)  # port 0: any free port, loopback only
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_demo_runs_to_show_done(repo):
    from playwright.sync_api import sync_playwright

    out = Path(os.environ.get("KHQS_EVIDENCE_DIR", "/srv/workdata/build-cache/khqs-evidence/p0"))
    out.mkdir(parents=True, exist_ok=True)
    srv = _serve(repo / "stage")
    errors, bad_responses = [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
            page.on("response", lambda r: r.status >= 400 and bad_responses.append((r.status, r.url)))
            t0 = time.monotonic()
            page.goto(f"http://127.0.0.1:{srv.server_port}/index.html#demo")
            shots = list(SHOT_TIMES_S)
            done = False
            while time.monotonic() - t0 < DEMO_TIMEOUT_S:
                if page.evaluate("window.KHQS_showDone === true"):
                    done = True
                    break
                if shots and time.monotonic() - t0 >= shots[0]:
                    page.screenshot(path=str(out / f"demo_{shots.pop(0):03d}s.png"))
                page.wait_for_timeout(500)
            elapsed = time.monotonic() - t0
            page.screenshot(path=str(out / "demo_end.png"))
            browser.close()
    finally:
        srv.shutdown()
    print(f"demo elapsed {elapsed:.1f}s done={done}; errors={errors}; bad responses={bad_responses}")
    assert done, f"KHQS_showDone not set within {DEMO_TIMEOUT_S}s"
    # Allow only the missing favicon (no <link rel=icon>, so the browser asks for /favicon.ico).
    real_errors = [e for e in errors if "favicon" not in e and "404" not in e]
    assert real_errors == []
    assert [b for b in bad_responses if not b[1].endswith("/favicon.ico")] == []
