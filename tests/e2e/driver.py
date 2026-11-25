"""Headless-browser driver: the real stage, the screen pad (iframe) and phone pages, played like people.

Everything a player does goes through the phone UI (select, then LOCK IN). The driver reads the engine only to
decide *what* to answer (it knows the content) and to assert; it never injects actions into the engine.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/srv/workdata/browser-cache/ms-playwright")

EVIDENCE = os.environ.get("KHQS_EVIDENCE_DIR", "/srv/workdata/build-cache/khqs-evidence/p2")
LAUNCH_ARGS = ["--autoplay-policy=no-user-gesture-required"]
NEW_SHOW = 'button:has-text("NEW SHOW ▶")'


@dataclass
class Player:
    name: str
    kind: str  # pad | phone
    seat: int = -1
    target: object = None  # Page or Frame with the controller
    page: object = None
    reloaded: bool = False
    log: list = field(default_factory=list)

    def view(self):
        try:
            return self.target.evaluate("window.KHQS_PHONE && window.KHQS_PHONE.view")
        except Exception:  # navigation in progress (reload)
            return None


class Show:
    def __init__(self, pw, srv, tag: str, extra_args=()):
        self.pw, self.srv, self.tag = pw, srv, tag
        self.browser = pw.chromium.launch(args=[*LAUNCH_ARGS, *extra_args])
        self.errors: list[str] = []
        self.frames: list[tuple[str, dict]] = []
        self.players: list[Player] = []
        self.stage = self._new_page(self.browser.new_context(viewport={"width": 1600, "height": 900}, permissions=["microphone"]), "stage")
        self.ports = srv.settings
        self.acted: set = set()
        self.samples: list[dict] = []
        os.makedirs(EVIDENCE, exist_ok=True)

    # ------------------------------------------------------------------ plumbing
    def _new_page(self, ctx, who):
        page = ctx.new_page()
        page.on("pageerror", lambda e, w=who: self.errors.append(f"{w}: pageerror {e}"))
        page.on("console", lambda m, w=who: m.type == "error" and "fonts.g" not in (m.location.get("url", "") if m.location else "")
                and self.errors.append(f"{w}: console {m.text}"))
        page.on("websocket", lambda ws, w=who: self._watch(ws, w))
        return page

    def _watch(self, ws, who):
        who = f"{who}:{'stage' if '/ws/stage' in ws.url else 'phone'}"  # which socket the frames came from

        def got(payload):
            try:
                self.frames.append((who, json.loads(payload)))
            except (ValueError, TypeError):
                pass
        ws.on("framereceived", got)

    @property
    def eng(self):
        return self.srv.host.engine

    def shot(self, name):
        self.stage.screenshot(path=f"{EVIDENCE}/{self.tag}_{name}.png")

    def close(self):
        self.browser.close()

    # ------------------------------------------------------------------ lobby
    def open_stage(self):
        s = self.ports
        self.stage.goto(f"http://127.0.0.1:{s.stage_port}/")
        self.stage.wait_for_function("window.KHQS_LIVE && KHQS_LIVE.status === 'online' && document.querySelector('.cb-entry input')", timeout=30000)

    def join_pad(self, name):
        inp = self.stage.locator(".cb-entry input")
        inp.fill(name)
        inp.press("Enter")
        self.stage.wait_for_function("name => [...document.querySelectorAll('#khqs-pad iframe')].some(f => f.title.includes(name))", arg=name, timeout=15000)
        p = Player(name, "pad", page=self.stage)
        self._seat(p)
        self.players.append(p)
        self._attach_pad(p)
        return p

    def _attach_pad(self, p):
        fr = None
        for _ in range(100):
            fr = next((f for f in self.stage.frames if f.url.endswith(f"/phone?pad={p.seat}")), None)
            if fr:
                try:
                    fr.wait_for_function("window.KHQS_PHONE && window.KHQS_PHONE.view", timeout=500)
                    break
                except Exception:
                    pass
            self.stage.wait_for_timeout(100)
        assert fr, "pad iframe never became ready"
        p.target = fr

    def join_phone(self, name):
        s = self.ports
        ctx = self.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page = self._new_page(ctx, f"phone-{name}")
        page.goto(f"http://127.0.0.1:{s.phone_port}/ticket.html")
        page.fill("#name", name)
        page.click("#go")
        page.wait_for_selector(".admitted", timeout=10000)
        page.wait_for_url("**/phone", timeout=10000)
        page.wait_for_function("window.KHQS_PHONE && window.KHQS_PHONE.view", timeout=10000)
        p = Player(name, "phone", page=page, target=page)
        self._seat(p)
        self.players.append(p)
        return p

    def _seat(self, p):
        p.seat = next(s for s, pl in self.eng.players.items() if pl.name == p.name)

    def start_show(self):
        self.stage.wait_for_function("(() => { const b = document.querySelector('.cb-sign'); return b && !b.disabled; })()", timeout=30000)
        self.shot("lobby_full")
        self.stage.evaluate("document.querySelector('.cb-sign').click()")

    # ------------------------------------------------------------------ playing
    def once(self, key) -> bool:
        if key in self.acted:
            return False
        self.acted.add(key)
        return True

    def click_lock(self, p, sel):
        p.target.click(sel)
        p.target.click("#lock")

    def tick(self, plan):
        eng = self.eng
        q = eng.q
        qn = q.number if q else 0
        for p in self.players:
            v = p.view()
            if not v:
                continue
            scr = v["screen"]
            seat = p.seat
            if scr == "ox" and self.once(("ox", qn, seat)):
                if qn == 1:  # prove select-then-lock: a tap alone sends nothing
                    p.target.click('[data-choice="X"]')
                    self.stage.wait_for_timeout(400)
                    assert seat not in eng.round.picks, "a selection alone must not be sent"
                self.click_lock(p, f'[data-choice="{plan["ox"](seat, qn)}"]')
            elif scr == "betrayal_reason" and self.once(("reason", qn, seat)):
                self.click_lock(p, "[data-reason]")
            elif scr == "betrayal_decision" and self.once(("decision", qn, seat)):
                self.click_lock(p, '[data-decision="switch"]')
            elif scr == "buzzer":
                who = plan["buzz"](qn, len(eng.round.attempts), eng.phase)
                if who == seat and self.once(("buzz", qn, len(eng.round.attempts), eng.phase)):
                    p.target.click("#buzz")
            elif scr == "answer_text" and self.once(("text", qn, seat, len(eng.round.attempts))):
                p.target.fill("#answer-text", plan["text"](qn, seat, len(eng.round.attempts)))
                p.target.click("#send-answer")
            elif scr == "bet" and self.once(("bet", seat)):
                amt = plan["bet"](seat, eng.players[seat].score)
                p.target.eval_on_selector("#bet-range", "(e, v) => { e.value = v; e.dispatchEvent(new Event('input')); }", amt)
                p.target.click("#lock")
            elif scr == "final_choice" and self.once(("choice", seat)):
                self.click_lock(p, f'[data-choice="{plan["final"](seat)}"]')
            self.sample_view(p, v)

    def sample_view(self, p, v):
        p.log.append(v["screen"])
        key = ("shot", p.name, v["screen"])
        if p.kind == "phone" and key not in self.acted:  # one picture per phone screen, as evidence of the UI
            self.acted.add(key)
            try:
                p.target.screenshot(path=f"{EVIDENCE}/{self.tag}_phone_{v['screen']}.png")
            except Exception:
                pass

    def play(self, plan, reload_at=None, timeout=900):
        """Run until the engine says `ended`. `reload_at(engine) -> Player|None` may ask for a reload."""
        t0 = time.monotonic()
        while self.eng.phase != "ended":
            if time.monotonic() - t0 > timeout:
                raise TimeoutError(f"game did not end; phase={self.eng.phase} q={self.eng.question_no}")
            self.tick(plan)
            self.sample_stage()
            if reload_at:
                who = reload_at(self.eng)
                if who and not who.reloaded and self.once(("reload", who.seat)):
                    who.reloaded = True
                    if who.kind == "phone":
                        who.page.reload()
                        who.page.wait_for_function("window.KHQS_PHONE && window.KHQS_PHONE.view", timeout=15000)
                    else:
                        who.target.evaluate("location.reload()")
                        self.stage.wait_for_timeout(500)
                        self._attach_pad(who)
            self.stage.wait_for_timeout(250)

    def sample_stage(self):
        live = self.stage.evaluate("window.KHQS_LIVE && {role: KHQS_LIVE.role, status: KHQS_LIVE.status}")
        self.samples.append({"t": time.monotonic(), "live": live, "phase": self.eng.phase})

    # ------------------------------------------------------------------ the end
    def finale_checks(self):
        """Podium drawn; NEW SHOW appears only after game.ended. Returns evidence."""
        ev = {"early_new_show": False, "saw_new_show": False}
        t0 = time.monotonic()
        while time.monotonic() - t0 < 60 and not ev["saw_new_show"]:
            visible = self.stage.locator(NEW_SHOW).count() > 0 and self.stage.locator(NEW_SHOW).first.is_visible()
            ended = any(m["type"] == "game.ended" for m in self.eng.stream)
            if visible and not ended:
                ev["early_new_show"] = True
            ev["saw_new_show"] = visible
            self.stage.wait_for_timeout(100)
        self.stage.wait_for_function("window.KHQS_showDone === true", timeout=30000)
        self.shot("podium")
        ev["pods"] = self.stage.evaluate("[...document.images].filter(i => /fin_pod/.test(i.src) && i.offsetParent !== null).length")
        return ev

    def new_show(self):
        g0 = self.eng.game_id
        self.stage.click(NEW_SHOW)
        self.stage.wait_for_function("KHQS_LIVE.phase === 'lobby'", timeout=20000)
        self.stage.wait_for_function("!!document.querySelector('.cb-entry input')", timeout=20000)
        assert self.eng.game_id != g0
        self.shot("new_lobby")
