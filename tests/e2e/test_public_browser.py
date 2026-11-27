"""Public demo mode in a real browser: a visitor through the public host name, and the owner on 127.0.0.1.

Chromium maps demo.example.com to 127.0.0.1 (as the tunnel would deliver it). No tunnel, no deployment.
Slow-ish (about a minute):  scripts/test.sh -m slow tests/e2e/test_public_browser.py
"""
import pytest
from playwright.sync_api import expect, sync_playwright

from khqs.server.runner import RunningServer
from khqs.server.settings import Settings
from driver import LAUNCH_ARGS
from server_helpers import free_port

pytestmark = pytest.mark.slow
HOST, SECRET = "demo.example.com", "browser-test-operator-secret-77"


def test_public_visitor_and_local_operator_in_real_browsers():
    s = Settings(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True, record=True, seed=9,
                 mock_speed=2.0, join_grace_s=60.0, public=True, public_host=HOST, operator_secret=SECRET).validate()
    srv = RunningServer(s).start()
    port = s.stage_port
    errors = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(args=[*LAUNCH_ARGS, f"--host-resolver-rules=MAP {HOST} 127.0.0.1"])
            # ---- a public visitor
            pub = b.new_context(viewport={"width": 1600, "height": 900}).new_page()
            pub.on("pageerror", lambda e: errors.append(str(e)))
            pub.goto(f"http://{HOST}:{port}/")
            pub.wait_for_function("window.KHQS_LIVE && KHQS_LIVE.status === 'online' && document.querySelector('.cb-entry input')", timeout=30000)
            assert pub.evaluate("KHQS_LIVE.mc") == "mock" and pub.evaluate("KHQS_LIVE.role") == "primary"
            assert pub.locator("#khqs-chip .new").count() == 0 and pub.locator("#khqs-chip .take").count() == 0 and pub.locator("#khqs-chip .mcre").count() == 0
            expect(pub.locator("#khqs-chip .restart")).to_be_hidden()
            assert HOST in pub.evaluate("window.KHQS_JOIN_URL") and pub.evaluate("window.KHQS_JOIN_URL").startswith("https://")
            inp = pub.locator(".cb-entry input")
            inp.fill("Mina")
            inp.press("Enter")
            pub.wait_for_function("document.querySelectorAll('#khqs-pad iframe').length === 1", timeout=15000)
            # a second public tab is a viewer; it cannot start the show, and take-over is not offered
            viewer = b.new_context().new_page()
            viewer.on("pageerror", lambda e: errors.append(str(e)))
            viewer.goto(f"http://{HOST}:{port}/")
            viewer.wait_for_function("window.KHQS_LIVE && KHQS_LIVE.role === 'viewer'", timeout=30000)
            assert viewer.locator("#khqs-chip .take").count() == 0
            restart = viewer.locator("#khqs-chip .restart")
            expect(restart).to_be_visible()
            status = viewer.evaluate("fetch('/api/start', {method: 'POST', headers: {'X-KHQS': '1', 'X-KHQS-Cid': 'not-the-main-screen'}}).then(r => r.status)")
            assert status == 403 and srv.host.engine.phase == "lobby"
            # the main screen starts the show (the connector sends its client id)
            pub.wait_for_function("(() => { const b = document.querySelector('.cb-sign'); return b && !b.disabled; })()", timeout=30000)
            pub.evaluate("document.querySelector('.cb-sign').click()")
            pub.wait_for_function("KHQS_LIVE.phase !== 'lobby'", timeout=30000)
            assert srv.host.engine.phase != "lobby"
            expect(restart).to_be_hidden()
            expect(pub.locator("#khqs-chip .restart")).to_be_visible()
            # a public page can never reach operator endpoints, even with the secret in hand
            res = pub.evaluate(f"fetch('/api/reset', {{method: 'POST', headers: {{'X-KHQS': '1', 'X-KHQS-Operator': '{SECRET}'}}, body: JSON.stringify({{force: true}})}}).then(r => r.status)")
            assert res == 403 and srv.host.game_index == 0
            # ---- the owner on 127.0.0.1: operator buttons, the secret is asked for and kept only in page memory
            owner_ctx = b.new_context(viewport={"width": 1600, "height": 900})
            owner = owner_ctx.new_page()
            answers = ["wrong-secret", SECRET]
            prompts = []

            def on_dialog(d):
                if d.type == "prompt":
                    prompts.append(d.message)
                    d.accept(answers.pop(0))
                else:
                    d.accept()
            owner.on("dialog", on_dialog)
            owner.goto(f"http://127.0.0.1:{port}/")
            owner.wait_for_function("window.KHQS_LIVE && KHQS_LIVE.status === 'online'", timeout=30000)
            assert owner.locator("#khqs-chip .new").count() == 1
            assert owner.locator("#khqs-chip .restart").count() == 0
            assert SECRET not in owner.content() and SECRET not in owner.evaluate("JSON.stringify(Object.assign({}, localStorage, sessionStorage))")
            owner.click("#khqs-chip .new")
            owner.wait_for_timeout(1500)
            assert srv.host.game_index == 0 and len(prompts) == 1  # a wrong secret does nothing
            owner.click("#khqs-chip .new")  # the secret is asked for again after a refusal
            owner.wait_for_function("true")
            for _ in range(40):
                if srv.host.game_index == 1:
                    break
                owner.wait_for_timeout(250)
            assert srv.host.game_index == 1 and len(prompts) == 2 and srv.host.engine.phase == "lobby"
            assert SECRET not in owner.content() and SECRET not in pub.content()

            # The viewer can rescue the fresh lobby, with an inline confirmation and no navigation.
            expect(restart).to_be_visible()
            restart.click()
            expect(restart).to_have_text("SURE? ↻")
            assert srv.host.game_index == 1
            expect(restart).to_have_text("RESTART")
            restart.click()
            restart.click()
            expect(viewer.locator("#khqs-chip")).to_have_attribute("data-role", "primary")
            expect(restart).to_be_hidden()
            expect(pub.locator("#khqs-chip")).to_have_attribute("data-role", "viewer")
            expect(pub.locator("#khqs-chip")).to_have_attribute("data-phase", "lobby")
            expect(viewer.locator(".cb-entry input")).to_be_visible()
            expect(pub.locator(".cb-entry input")).to_be_visible()
            assert srv.host.game_index == 2 and not srv.host.engine.players
            pub.reload()
            expect(pub.locator("#khqs-chip")).to_have_attribute("data-role", "viewer")
            expect(pub.locator("#khqs-chip .restart")).to_be_visible()
            assert errors == [], errors
            b.close()
    finally:
        srv.stop()
