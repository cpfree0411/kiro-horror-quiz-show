"""The two ASGI apps. The phone app gets a strict subset of the stage app's routes."""
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

from . import pages
from ..mc.live import LiveMc
from ..mc.transport import LiveError
from .host import Conn, GameHost
from .settings import LOOPBACK_NAMES, Settings

PHONE_MAX_BYTES = 2048
PHONE_RATE = 20  # messages per second
PHONE_MAX_SOCKS = 4
STAGE_MAX_BYTES = 65536
HELLO_TIMEOUT = 5.0
JOIN_MAX_BYTES = 1024
NOCACHE = {"Cache-Control": "no-store"}

# Route tables, used by the apps and by the port-split test.
PHONE_PATHS = ("/ticket.html", "/phone", "/phone/phone.css", "/phone/phone.js", "/play/ticket-hook.js", "/api/join", "/ws/phone")
STAGE_ONLY_PATHS = ("/", "/index.html", "/stage.js", "/assets/manifest.js", "/play/link.js", "/play/mc-audio.js", "/stage/assets/a-3f9c1d2e7b40",
                    "/api/start", "/api/reset", "/api/mc/connect", "/api/mc/disconnect", "/api/mc/status", "/ws/stage", "/ws/mc")


def _hostname(host_header: str) -> str:
    h = host_header.strip()
    if h.startswith("["):
        return h[1: h.index("]")]
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def same_origin(headers) -> bool:
    """A browser Origin, when present, must be this very server (blocks cross-site WebSocket and POST)."""
    origin = headers.get("origin")
    return origin is None or origin in (f"http://{headers.get('host', '')}", f"https://{headers.get('host', '')}")


def stage_request_ok(headers) -> bool:
    """Stage app: loopback host names only (DNS rebinding) and a same-origin Origin."""
    return _hostname(headers.get("host", "")) in LOOPBACK_NAMES and same_origin(headers)


def build_apps(host: GameHost, settings: Settings) -> tuple[Starlette, Starlette]:
    media = pages.MediaStore(settings.media_dir, {t.asset_id: t.file for t in host.bank.tracks})
    stage_dir = settings.stage_dir
    web = pages.WEB

    # ---------------------------------------------------------------- phone routes (both ports)
    async def ticket(request: Request):
        return Response(pages.ticket_html(stage_dir), media_type="text/html; charset=utf-8", headers=NOCACHE)

    async def phone_page(request: Request):
        return FileResponse(web / "phone.html", headers=NOCACHE)

    async def phone_asset(request: Request):
        name = request.path_params["name"]
        if name not in ("phone.css", "phone.js"):
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(web / name, headers=NOCACHE)

    async def ticket_hook(request: Request):
        return FileResponse(web / "ticket-hook.js", media_type="text/javascript", headers=NOCACHE)

    async def api_join(request: Request):
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
        if not same_origin(ws.headers):
            await ws.close(1008)
            return
        await ws.accept()
        sock = Conn(ws, "phone")
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
                    r = host.run(host.engine.phone_action, sock.seat, msg.get("action"))
                    sock.send({"type": "result", "id": msg.get("id"), "ok": r.ok, "error": r.error})
                elif kind == "ping":
                    sock.send({"type": "pong"})
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            pass
        finally:
            host.phone_closed(sock)
            sock.close(1000)

    # ---------------------------------------------------------------- stage-only routes
    async def index(request: Request):
        if not stage_request_ok(request.headers):
            return PlainTextResponse("forbidden", status_code=403)
        return Response(pages.index_html(stage_dir), media_type="text/html; charset=utf-8", headers=NOCACHE)

    async def link(request: Request):
        return Response(pages.link_js(settings.join_url, settings.mc), media_type="text/javascript", headers=NOCACHE)

    async def mc_audio_js(request: Request):
        return FileResponse(web / "mc-audio.js", media_type="text/javascript", headers=NOCACHE)

    async def stage_static(request: Request):
        p = pages.static_path(stage_dir, request.path_params["path"])
        if p is None:
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(p, media_type=pages.media_type(p))

    async def stage_media(request: Request):
        p = media.path_for(request.path_params["asset_id"])
        if p is None:
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    def operator_ok(request: Request) -> bool:
        return stage_request_ok(request.headers) and request.headers.get("x-khqs") == "1"

    def live() -> LiveMc | None:
        return host.mc if isinstance(host.mc, LiveMc) else None

    async def api_start(request: Request):
        if not operator_ok(request):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        if live() is not None and live().state != "online":
            return JSONResponse({"error": "MC OFFLINE — TRY AGAIN"})
        r = host.start()
        return JSONResponse({"ok": True} if r.ok else {"error": r.error})

    async def api_reset(request: Request):
        if not operator_ok(request):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        try:
            force = bool((json.loads(await request.body() or b"{}") or {}).get("force"))
        except (ValueError, AttributeError):
            return JSONResponse({"error": "BAD REQUEST"}, status_code=400)
        r = host.reset(force)
        return JSONResponse({"ok": True} if r.ok else {"error": r.error})

    async def api_mc_connect(request: Request):
        if not operator_ok(request):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        mc = live()
        if mc is None:
            return JSONResponse({"ok": True, "mode": "mock"})
        try:
            await mc.connect()  # the only way a real session starts: an explicit operator action
        except LiveError as e:
            return JSONResponse({"error": "MC OFFLINE — TRY AGAIN", "detail": str(e)})
        return JSONResponse({"ok": True, "mode": "live"})

    async def api_mc_disconnect(request: Request):
        if not operator_ok(request):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        if live() is not None:
            await live().disconnect()
        return JSONResponse({"ok": True})

    async def api_mc_status(request: Request):
        if not stage_request_ok(request.headers):
            return JSONResponse({"error": "NOT ALLOWED"}, status_code=403)
        return JSONResponse(live().status() if live() else {"mode": "mock", "state": "online", "reason": "ok", "sessionsOpened": 0},
                            headers=NOCACHE)

    async def ws_mc(ws: WebSocket):
        mc = live()
        if mc is None or not stage_request_ok(ws.headers):
            await ws.close(1008)
            return
        await ws.accept()
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
        if not stage_request_ok(ws.headers):
            await ws.close(1008)
            return
        q = parse_qs(urlparse(str(ws.url)).query)
        cid = (q.get("cid") or [""])[0][:64]
        take = (q.get("take") or ["0"])[0] == "1"
        await ws.accept()
        sock = Conn(ws, "stage")
        sock.conn_id = host.new_conn_id()
        registered = False
        try:
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
        Route("/api/mc/connect", api_mc_connect, methods=["POST"]),
        Route("/api/mc/disconnect", api_mc_disconnect, methods=["POST"]),
        Route("/api/mc/status", api_mc_status),
        WebSocketRoute("/ws/mc", ws_mc),
        Route("/play/mc-audio.js", mc_audio_js),
        WebSocketRoute("/ws/stage", ws_stage),
        Route("/{path:path}", stage_static),  # last: frozen files by allowlist
    ]
    return Starlette(routes=phone_routes + stage_only), Starlette(routes=phone_routes)
