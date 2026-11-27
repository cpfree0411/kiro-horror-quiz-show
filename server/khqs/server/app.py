"""The two ASGI apps. The phone app (LAN) gets a strict subset of the stage app's routes.

Every stage-app handler starts with `admit()`, which classifies the request (local, public or refused), enforces the
private-show lock and the per-client limits, so a route cannot forget its guard (docs/PUBLIC_DEMO.md).
"""
from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import parse_qs, urlparse

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from ..mc.live import LiveMc
from ..mc.transport import LiveError
from . import guards, pages
from .host import Conn, GameHost
from .settings import Settings

PHONE_MAX_BYTES = 2048
PHONE_RATE = 20  # messages per second
PHONE_MAX_SOCKS = 4
STAGE_MAX_BYTES = 65536
HELLO_TIMEOUT = 5.0
JOIN_MAX_BYTES = 1024
NOCACHE = {"Cache-Control": "no-store"}
LAN = "lan"

# Route tables, used by the apps and by the port-split test.
PHONE_PATHS = ("/ticket.html", "/phone", "/phone/phone.css", "/phone/phone.js", "/play/ticket-hook.js", "/api/join", "/ws/phone")
STAGE_ONLY_PATHS = ("/", "/index.html", "/stage.js", "/assets/manifest.js", "/play/link.js", "/play/mc-audio.js", "/stage/assets/a-3f9c1d2e7b40",
                    "/api/start", "/api/reset", "/api/restart", "/api/mc/connect", "/api/mc/disconnect", "/api/mc/status", "/ws/stage", "/ws/mc")


def same_origin(headers) -> bool:
    """A browser Origin, when present, must be this very server (blocks cross-site WebSocket and POST)."""
    origin = headers.get("origin")
    return origin is None or origin in (f"http://{headers.get('host', '')}", f"https://{headers.get('host', '')}")


class SecurityHeaders:
    """Public responses get nosniff, no referrer and same-origin framing (the pad is a same-origin iframe)."""

    def __init__(self, app, settings: Settings) -> None:
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.settings.public:
            return await self.app(scope, receive, send)
        host = guards.hostname(dict((k.decode().lower(), v.decode("latin-1")) for k, v in scope["headers"]).get("host", ""))
        if host != self.settings.public_host.lower():
            return await self.app(scope, receive, send)

        async def send2(msg):
            if msg["type"] == "http.response.start":
                msg = dict(msg)
                msg["headers"] = [*msg["headers"], (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                                  (b"x-frame-options", b"SAMEORIGIN")]
            await send(msg)
        await self.app(scope, receive, send2)


def build_apps(host: GameHost, settings: Settings) -> tuple[Starlette, Starlette]:
    media = pages.MediaStore(settings.media_dir, {t.asset_id: t.file for t in host.bank.tracks})
    stage_dir = settings.stage_dir
    web = pages.WEB
    auth = guards.OperatorAuth(settings.operator_secret)
    lim_join = guards.RateLimiter(2, 300)
    lim_conn = guards.RateLimiter(30, 60)
    lim_act = guards.RateLimiter(6, 60)
    budget_stage = guards.SocketBudget(8, 12)
    budget_phone = guards.SocketBudget(8, 12)
    host.stats_providers.append(lambda: {"limiter_join": lim_join.size(), "limiter_conn": lim_conn.size(), "limiter_act": lim_act.size(),
                                         "budget_stage": budget_stage.count, "budget_phone": budget_phone.count,
                                         "budget_keys": budget_stage.size() + budget_phone.size()})

    # ---------------------------------------------------------------- admission
    def who(r) -> tuple[str | None, str]:
        """(class, client address): lan | local | public | None."""
        server = r.scope.get("server") or (None, None)
        peer = r.client.host if r.client else ""
        if server[1] == settings.phone_port:
            return LAN, peer
        return guards.classify(r.headers, peer, settings), guards.client_ip(r.headers, peer)

    def admit(r, limiter: guards.RateLimiter | None = None):
        """-> (class, ip, error response or None). Refuses unknown hosts, a private show, and clients over their limit."""
        k, ip = who(r)
        if k is None:
            return None, ip, PlainTextResponse("forbidden", status_code=403)
        if k == guards.PUBLIC:
            if host.private_show:
                return k, ip, JSONResponse({"error": "PRIVATE SHOW IN PROGRESS"}, status_code=503)
            if limiter is not None and not limiter.allow(ip):
                return k, ip, JSONResponse({"error": "TOO MANY TRIES. WAIT A BIT"}, status_code=429)
        return k, ip, None

    def operator(r, need_header: bool = True):
        """Operator actions: a local client, the custom header (not for a plain GET), and (public mode, or whenever one is set) the secret."""
        k, ip = who(r)
        if k != guards.LOCAL or (need_header and r.headers.get("x-khqs") != "1") or not same_origin(r.headers):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        if settings.public or auth.enabled:
            res = auth.check(ip, r.headers.get(guards.SECRET_HEADER))
            if res == "locked":
                return JSONResponse({"error": "TOO MANY WRONG SECRETS. WAIT A MINUTE"}, status_code=429)
            if res != "ok":
                return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        return None

    def show_action(r):
        """start / normal reset. Local clients as before; a public client must be the primary stage page."""
        k, ip, err = admit(r, lim_act)
        if err is not None:
            return err
        if r.headers.get("x-khqs") != "1" or not same_origin(r.headers):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        if k == guards.PUBLIC and (host.primary_cid() is None or r.headers.get("x-khqs-cid") != host.primary_cid()):
            return JSONResponse({"error": "ONLY THE MAIN SCREEN CAN DO THAT"}, status_code=403)
        return None

    # ---------------------------------------------------------------- phone routes (LAN port, and the stage port)
    async def ticket(request: Request):
        _, _, err = admit(request)
        return err or Response(pages.ticket_html(stage_dir), media_type="text/html; charset=utf-8", headers=NOCACHE)

    async def phone_page(request: Request):
        _, _, err = admit(request)
        return err or FileResponse(web / "phone.html", headers=NOCACHE)

    async def phone_asset(request: Request):
        _, _, err = admit(request)
        if err is not None:
            return err
        name = request.path_params["name"]
        if name not in ("phone.css", "phone.js"):
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(web / name, headers=NOCACHE)

    async def ticket_hook(request: Request):
        _, _, err = admit(request)
        return err or FileResponse(web / "ticket-hook.js", media_type="text/javascript", headers=NOCACHE)

    async def api_join(request: Request):
        k, ip, err = admit(request, lim_join)
        if err is not None:
            return err
        if request.headers.get("x-khqs") != "1" or not same_origin(request.headers):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        body = await request.body()
        if len(body) > JOIN_MAX_BYTES:
            return JSONResponse({"error": "TOO BIG"}, status_code=413)
        try:
            name = json.loads(body or b"{}").get("name")
        except (ValueError, AttributeError):
            return JSONResponse({"error": "BAD REQUEST"}, status_code=400)
        r = host.join(name)
        if not r.ok:
            return JSONResponse({"error": r.error})
        return JSONResponse({"ok": True, "seat": r.data["seat"], "credential": r.data["credential"]}, headers=NOCACHE)

    async def ws_phone(ws: WebSocket):
        k, ip = who(ws)
        if k is None or not same_origin(ws.headers) or (k == guards.PUBLIC and (host.private_show or not lim_conn.allow(ip)
                                                                              or not budget_phone.acquire(ip))):
            await ws.close(1008)
            return
        held = k == guards.PUBLIC
        await ws.accept()
        sock = Conn(ws, "phone")
        sock.klass, sock.ip = k, ip
        registered = False
        tokens, stamp = float(PHONE_RATE), time.monotonic()
        try:
            while True:
                if registered:
                    text = await ws.receive_text()
                else:
                    text = await asyncio.wait_for(ws.receive_text(), HELLO_TIMEOUT)
                now = time.monotonic()
                tokens = min(float(PHONE_RATE), tokens + (now - stamp) * PHONE_RATE)
                stamp = now
                tokens -= 1
                if len(text) > PHONE_MAX_BYTES or tokens < 0:
                    sock.close(1009 if len(text) > PHONE_MAX_BYTES else 1008)
                    return
                try:
                    msg = json.loads(text)
                    kind = msg["type"]
                except (ValueError, KeyError, TypeError):
                    sock.close(1008)
                    return
                if not registered:
                    if kind != "hello" or not isinstance(msg.get("cred"), str):
                        sock.close(1008)
                        return
                    seat = host.engine.seat_for_credential(msg["cred"])
                    if seat is not None and host.phone_count(seat) >= PHONE_MAX_SOCKS:
                        sock.close(1008)
                        return
                    if not host.phone_hello(sock, msg["cred"]):
                        sock.send({"type": "error", "code": "bad_cred"})
                        await asyncio.sleep(0.05)
                        sock.close(4003)
                        return
                    registered = True
                elif kind == "action":
                    host.touch_input()
                    r = host.run(host.engine.phone_action, sock.seat, msg.get("action"))
                    sock.send({"type": "result", "id": msg.get("id"), "ok": r.ok, "error": r.error})
                elif kind == "ping":
                    sock.send({"type": "pong"})
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            pass
        finally:
            if held:
                budget_phone.release(ip)
            host.phone_closed(sock)
            sock.close(1000)

    # ---------------------------------------------------------------- stage-only routes
    async def index(request: Request):
        _, _, err = admit(request)
        return err or Response(pages.index_html(stage_dir), media_type="text/html; charset=utf-8", headers=NOCACHE)

    async def link(request: Request):
        k, _, err = admit(request)
        if err is not None:
            return err
        public_client = k == guards.PUBLIC
        mc = "mock" if public_client else settings.mc  # strangers always get the mock MC
        return Response(pages.link_js(settings.join_url, mc, operator=k == guards.LOCAL, secret_required=bool(settings.public or settings.operator_secret)),
                        media_type="text/javascript", headers=NOCACHE)

    async def mc_audio_js(request: Request):
        k, _, err = admit(request)
        if err is None and k != guards.LOCAL:
            err = PlainTextResponse("not found", status_code=404)
        return err or FileResponse(web / "mc-audio.js", media_type="text/javascript", headers=NOCACHE)

    async def stage_static(request: Request):
        _, _, err = admit(request)
        if err is not None:
            return err
        p = pages.static_path(stage_dir, request.path_params["path"])
        if p is None:
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(p, media_type=pages.media_type(p))

    async def stage_media(request: Request):
        _, _, err = admit(request)
        if err is not None:
            return err
        p = media.path_for(request.path_params["asset_id"])
        if p is None:
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    def live() -> LiveMc | None:
        return host.live_mc

    async def api_start(request: Request):
        err = show_action(request)
        if err is not None:
            return err
        if isinstance(host.mc, LiveMc) and host.mc.state != "online":
            return JSONResponse({"error": "MC OFFLINE — TRY AGAIN"})
        r = host.start()
        return JSONResponse({"ok": True} if r.ok else {"error": r.error})

    async def api_reset(request: Request):
        try:
            force = bool((json.loads(await request.body() or b"{}") or {}).get("force"))
        except (ValueError, AttributeError):
            return JSONResponse({"error": "BAD REQUEST"}, status_code=400)
        err = operator(request) if force else show_action(request)
        if err is not None:
            return err
        r = host.reset(force)
        return JSONResponse({"ok": True} if r.ok else {"error": r.error})

    async def api_restart(request: Request):
        k, _, err = admit(request, lim_act)
        if err is not None:
            return err
        if k != guards.PUBLIC:
            return JSONResponse({"error": "NOT FOUND"}, status_code=404)
        if request.headers.get("x-khqs") != "1" or not same_origin(request.headers):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        sock = host.public_stage(request.headers.get("x-khqs-cid"))
        if sock is None:
            return JSONResponse({"error": "STAGE CONNECTION REQUIRED"}, status_code=403)
        r = host.restart(sock)
        return JSONResponse({"ok": True}) if r.ok else JSONResponse({"error": r.error}, status_code=409)

    async def api_mc_connect(request: Request):
        err = operator(request)
        if err is not None:
            return err
        mc = live()
        if mc is None:
            return JSONResponse({"ok": True, "mode": "mock"})
        if settings.public and (host.has_public_clients() or host.engine.players or host.engine.phase != "lobby"):
            return JSONResponse({"error": "NOT NOW: PUBLIC PLAYERS ARE CONNECTED OR A GAME IS RUNNING"})
        try:
            await mc.connect()  # the only way a real session starts: an explicit operator action
        except LiveError as e:
            return JSONResponse({"error": "MC OFFLINE — TRY AGAIN", "detail": str(e)})
        return JSONResponse({"ok": True, "mode": "live"})

    async def api_mc_disconnect(request: Request):
        err = operator(request)
        if err is not None:
            return err
        if live() is not None:
            await live().disconnect()
        return JSONResponse({"ok": True})

    async def api_mc_status(request: Request):
        err = operator(request, need_header=False)
        if err is not None:
            return err
        mc = live()
        return JSONResponse(mc.status() if mc else {"mode": "mock", "state": "online", "reason": "ok", "sessionsOpened": 0}, headers=NOCACHE)

    async def api_diag(request: Request):
        if not settings.diag:
            return PlainTextResponse("not found", status_code=404)
        err = operator(request, need_header=False)
        if err is not None:
            return err
        from .stats import process_stats
        return JSONResponse(process_stats(host), headers=NOCACHE)

    async def ws_mc(ws: WebSocket):
        mc = live()
        k, ip = who(ws)
        if mc is None or k != guards.LOCAL or not same_origin(ws.headers):
            await ws.close(1008)
            return
        await ws.accept()
        if settings.public or auth.enabled:  # a browser cannot send headers on a WebSocket: the secret is the first frame, never in the URL
            try:
                first = json.loads(await asyncio.wait_for(ws.receive_text(), HELLO_TIMEOUT))
                ok = first.get("t") == "hello" and auth.check(ip, first.get("secret")) == "ok"
            except (ValueError, AttributeError, asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
                ok = False
            if not ok:
                await ws.close(4003)
                return
        sock = Conn(ws, "mc")
        old = host.mc_port.conn
        host.mc_port.conn = sock
        if old is not None:
            old.close(4001)
        try:
            while True:
                m = await ws.receive()
                if m["type"] == "websocket.disconnect":
                    break
                if m.get("bytes") is not None:
                    if len(m["bytes"]) <= 8192:
                        await mc.on_mic(m["bytes"])
                elif m.get("text"):
                    try:
                        msg = json.loads(m["text"])
                        token = msg.get("k")
                    except (ValueError, AttributeError):
                        continue
                    if msg.get("t") == "started" and isinstance(token, str):
                        mc.on_started(token)
                    elif msg.get("t") == "played" and isinstance(token, str):
                        mc.on_played(token)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if host.mc_port.conn is sock:
                host.mc_port.conn = None
                if mc.state == "online":
                    await mc.safe_stop("the browser audio disconnected")
            sock.close(1000)

    async def ws_stage(ws: WebSocket):
        k, ip = who(ws)
        if k is None or not same_origin(ws.headers) or k == LAN:
            await ws.close(1008)
            return
        public_client = k == guards.PUBLIC
        if public_client and (host.private_show or not lim_conn.allow(ip) or not budget_stage.acquire(ip)):
            await ws.close(1008)
            return
        q = parse_qs(urlparse(str(ws.url)).query)
        cid = (q.get("cid") or [""])[0][:64]
        take = (q.get("take") or ["0"])[0] == "1"
        if take and public_client:
            if public_client:
                budget_stage.release(ip)
            await ws.close(1008)  # taking over the main screen is an operator action
            return
        await ws.accept()
        sock = Conn(ws, "stage")
        sock.klass, sock.ip = k, ip
        sock.conn_id = host.new_conn_id()
        registered = False
        try:
            if take and (settings.public or auth.enabled):  # the secret travels in a frame before the hello, never in the URL
                try:
                    first = json.loads(await asyncio.wait_for(ws.receive_text(), HELLO_TIMEOUT))
                    ok = first.get("type") == "khqs.operator" and auth.check(ip, first.get("secret")) == "ok"
                except (ValueError, AttributeError, asyncio.TimeoutError):
                    ok = False
                if not ok:
                    sock.close(4003)
                    return
            while True:
                text = await (ws.receive_text() if registered else asyncio.wait_for(ws.receive_text(), HELLO_TIMEOUT))
                if len(text) > STAGE_MAX_BYTES:
                    sock.close(1009)
                    return
                try:
                    msg = json.loads(text)
                except ValueError:
                    sock.close(1008)
                    return
                if not registered:
                    d = msg.get("data") if isinstance(msg, dict) else None
                    if not isinstance(d, dict) or msg.get("type") != "stage.hello" or d.get("role") not in ("primary", "viewer"):
                        sock.close(1008)
                        return
                    host.stage_hello(sock, d["role"], d.get("lastSseq"), cid, take)
                    registered = True
                else:
                    host.run(host.engine.stage_message, sock.conn_id, msg)
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            pass
        finally:
            if public_client:
                budget_stage.release(ip)
            host.stage_closed(sock)
            sock.close(1000)

    phone_routes = [
        Route("/ticket.html", ticket),
        Route("/phone", phone_page),
        Route("/phone/{name}", phone_asset),
        Route("/play/ticket-hook.js", ticket_hook),
        Route("/api/join", api_join, methods=["POST"]),
        WebSocketRoute("/ws/phone", ws_phone),
    ]
    stage_only = [
        Route("/", index),
        Route("/index.html", index),
        Route("/play/link.js", link),
        Route("/stage/assets/{asset_id}", stage_media),
        Route("/api/start", api_start, methods=["POST"]),
        Route("/api/reset", api_reset, methods=["POST"]),
        Route("/api/restart", api_restart, methods=["POST"]),
        Route("/api/mc/connect", api_mc_connect, methods=["POST"]),
        Route("/api/mc/disconnect", api_mc_disconnect, methods=["POST"]),
        Route("/api/mc/status", api_mc_status),
        Route("/api/diag", api_diag),
        WebSocketRoute("/ws/mc", ws_mc),
        Route("/play/mc-audio.js", mc_audio_js),
        WebSocketRoute("/ws/stage", ws_stage),
        Route("/{path:path}", stage_static),  # last: frozen files by allowlist
    ]
    stage_app = SecurityHeaders(Starlette(routes=phone_routes + stage_only), settings)
    return stage_app, Starlette(routes=phone_routes)
