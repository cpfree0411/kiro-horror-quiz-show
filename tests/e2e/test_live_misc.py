"""P2 acceptance, the rest: replay hashes leave the connector out; #demo on the live server; reload and take-over."""
import os

import pytest
from playwright.sync_api import sync_playwright

from khqs.server.runner import RunningServer
from khqs.server.settings import Settings
from driver import EVIDENCE, LAUNCH_ARGS
from server_helpers import free_port

pytestmark = pytest.mark.slow


def server(seed=21):
    return RunningServer(Settings(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True,
                                  record=True, seed=seed, mock_speed=2.0, join_grace_s=30.0).validate()).start()


def watch(page, errors):
    page.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
    page.on("console", lambda m: m.type == "error" and errors.append(f"console {m.text}"))


REPLAY_HASHES = ["#act=1", "#act=2&step=3", "#opening", "#showtime", "#opening&clean", "#act=1&verdict=1o", "#demo", "#act=3&finale=2", "#act=1&trans=act"]
LIVE_HASHES = ["", "#stay", "#cast=Mina,Junho", "#qr=http://example.invalid/x", "#badge=plain"]


def test_replay_and_demo_hashes_leave_the_connector_out_and_other_hashes_do_not():
    srv = server()
    os.makedirs(EVIDENCE, exist_ok=True)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(args=LAUNCH_ARGS)
            for h in REPLAY_HASHES:
                page = b.new_page(viewport={"width": 1600, "height": 900})
                errors = []
                watch(page, errors)
                page.goto(f"http://127.0.0.1:{srv.settings.stage_port}/{h}")
                page.wait_for_timeout(2500)
                state = page.evaluate("({live: typeof KHQS_LIVE, entry: typeof KHQS_ENTRY, join: typeof KHQS_JOIN_URL, chip: !!document.getElementById('khqs-chip'), mock: window.MockEngine && window.MockEngine.name})")
                assert state == {"live": "undefined", "entry": "undefined", "join": "undefined", "chip": False, "mock": "MockEngine"}, (h, state)
                assert errors == [], (h, errors)
                page.close()
            assert srv.host.stage == {}, "no replay hash may open a stage socket"
            for h in LIVE_HASHES:
                page = b.new_page(viewport={"width": 1600, "height": 900})
                page.goto(f"http://127.0.0.1:{srv.settings.stage_port}/{h}")
                page.wait_for_function("window.KHQS_LIVE && KHQS_LIVE.status === 'online'", timeout=15000)
                assert page.evaluate("typeof KHQS_ENTRY") == "object" and page.evaluate("window.MockEngine.name") == "LiveEngine", h
                page.close()
            b.close()
    finally:
        srv.stop()


def test_demo_plays_as_a_mock_on_the_live_server():
    srv = server()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(args=LAUNCH_ARGS)
            page = b.new_page(viewport={"width": 1600, "height": 900})
            errors = []
            watch(page, errors)
            page.goto(f"http://127.0.0.1:{srv.settings.stage_port}/#demo")
            elapsed = 0
            while elapsed < 380 and not page.evaluate("window.KHQS_showDone === true"):
                page.wait_for_timeout(1000)
                elapsed += 1
            assert page.evaluate("window.KHQS_showDone === true"), "the demo never finished"
            page.screenshot(path=f"{EVIDENCE}/demo_live_end.png")
            assert errors == [], errors
            assert srv.host.stage == {} and len(srv.host.engine.stream) == 1  # the real engine never saw the demo
            assert page.evaluate("typeof KHQS_LIVE") == "undefined"
            b.close()
    finally:
        srv.stop()


def test_stage_reload_keeps_primary_second_tab_is_viewer_and_take_over_is_stable():
    srv = server()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(args=LAUNCH_ARGS)
            ctx1 = b.new_context(viewport={"width": 1600, "height": 900})
            page = ctx1.new_page()
            errors = []
            watch(page, errors)
            base = f"http://127.0.0.1:{srv.settings.stage_port}/"
            page.goto(base)
            page.wait_for_function("window.KHQS_LIVE && KHQS_LIVE.status === 'online' && document.querySelector('.cb-entry input')", timeout=30000)
            inp = page.locator(".cb-entry input")
            inp.fill("Mina")
            inp.press("Enter")
            page.wait_for_function("document.querySelectorAll('#khqs-pad iframe').length === 1")
            page.wait_for_function("(() => { const b = document.querySelector('.cb-sign'); return b && !b.disabled; })()", timeout=30000)
            page.evaluate("document.querySelector('.cb-sign').click()")
            page.wait_for_function("KHQS_LIVE.phase === 'ox.presenting' || KHQS_LIVE.phase === 'ox.answering' || KHQS_LIVE.phase === 'act_intro'", timeout=120000)
            old_primary = srv.host.engine.primary
            gate_before = srv.host.engine.stats["gate_timeouts"]
            # --- reload the stage tab: same sessionStorage cid, so it must come back as primary at once
            page.reload()
            page.wait_for_function("window.KHQS_LIVE && KHQS_LIVE.status === 'online'", timeout=30000)
            page.wait_for_timeout(1500)
            assert page.evaluate("KHQS_LIVE.role") == "primary"
            assert srv.host.engine.primary is not None and srv.host.engine.primary != old_primary
            assert [c.role for c in srv.host.stage.values()] == ["primary"]
            # --- a second tab (own sessionStorage, other cid) is a viewer
            page2 = b.new_context(viewport={"width": 1600, "height": 900}).new_page()
            page2.goto(base)
            page2.wait_for_function("window.KHQS_LIVE && KHQS_LIVE.role === 'viewer'", timeout=30000)
            assert page2.locator("#khqs-chip .take").is_visible() and not page.locator("#khqs-chip .take").is_visible()
            assert sorted(c.role for c in srv.host.stage.values()) == ["primary", "viewer"]
            # --- explicit take-over: tab 2 becomes primary and tab 1 settles as a viewer, no flapping
            page2.click("#khqs-chip .take")
            page2.wait_for_function("KHQS_LIVE.role === 'primary'", timeout=10000)
            page.wait_for_function("KHQS_LIVE.role === 'viewer'", timeout=10000)
            primary_now = srv.host.engine.primary
            page.wait_for_timeout(4000)
            assert srv.host.engine.primary == primary_now and page.evaluate("KHQS_LIVE.role") == "viewer" and page2.evaluate("KHQS_LIVE.role") == "primary"
            assert errors == [], errors
            # the show keeps going on the new primary
            n = len(srv.host.engine.stream)
            for _ in range(240):
                if len(srv.host.engine.stream) > n + 3:
                    break
                page2.wait_for_timeout(250)
            assert len(srv.host.engine.stream) > n + 3, "the show stopped after the take-over"
            assert srv.host.engine.stats["gate_timeouts"] <= gate_before + 1  # at most the gate open during the reload
            b.close()
    finally:
        srv.stop()
