"""Public demo mode: every guard in docs/PUBLIC_DEMO.md, against a real server with tunnel-style requests.

The tunnel (cloudflared) connects from loopback with the public Host header and a CF-Connecting-IP header; these tests
send exactly that. Nothing is deployed and no tunnel is involved.
"""
import json
import logging
import socket
import time

import pytest
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus
from websockets.sync.client import connect

from khqs.server.runner import RunningServer
from live_rig import FakeTransport
from net import get, hello, post
from settings_util import make_settings

HOST = "demo.example.com"
SECRET = "correct-horse-battery-staple-42"
TUNNEL = {"Host": HOST, "CF-Connecting-IP": "203.0.113.5", "X-Forwarded-For": "203.0.113.5"}


@pytest.fixture
def pub():
    srv = RunningServer(make_settings(public=True, public_host=HOST, operator_secret=SECRET, join_grace_s=60.0)).start()
    yield srv
    srv.stop()


def base(srv):
    return f"http://127.0.0.1:{srv.settings.stage_port}"


def tunnel(ip="203.0.113.5", **extra):
    return {"Host": HOST, "CF-Connecting-IP": ip, "X-Forwarded-For": ip, **extra}


def pws(srv, path, ip="203.0.113.5", headers=None, host=HOST):
    """A WebSocket as the tunnel would deliver it: loopback peer, public Host, same-origin Origin."""
    port = srv.settings.stage_port
    sock = socket.create_connection(("127.0.0.1", port))
    h = {"Origin": f"http://{host}:{port}", "CF-Connecting-IP": ip, **(headers or {})}
    return connect(f"ws://{host}:{port}{path}", sock=sock, additional_headers=h, open_timeout=5)


def op(extra=None, secret=SECRET):
    h = {"X-KHQS-Operator": secret}
    h.update(extra or {})
    return h


def closed(ws, wait=2.0):
    end = time.monotonic() + wait
    while time.monotonic() < end:
        try:
            ws.recv(timeout=max(0.05, end - time.monotonic()))
        except ConnectionClosed:
            return True
        except TimeoutError:
            return False
    return False


# ---------------------------------------------------------------- who is asking
def test_local_public_and_everything_else(pub):
    b = base(pub)
    assert get(b + "/")[0] == 200  # local: loopback host, no forwarding headers
    assert get(b + "/", tunnel())[0] == 200  # public: the tunnel's Host
    assert get(b + "/", {"Host": "evil.example"})[0] == 403
    assert get(b + "/", {"Host": f"127.0.0.1:{pub.settings.stage_port}", "X-Forwarded-For": "1.2.3.4"})[0] == 403  # proxied: never local
    assert get(b + "/", {"Host": f"127.0.0.1:{pub.settings.stage_port}", "CF-Connecting-IP": "1.2.3.4"})[0] == 403
    assert get(b + "/", {"Host": "demo.example.com.evil.example"})[0] == 403
    assert get(b + "/stage.js", tunnel())[0] == 200 and get(b + "/ticket.html", tunnel())[0] == 200
    assert get(b + "/phone", tunnel())[0] == 200 and get(b + "/stage/assets/a-3f9c1d2e7b40", tunnel())[0] == 200


def test_without_public_mode_the_public_host_is_refused(server):
    assert get(f"http://127.0.0.1:{server.settings.stage_port}/", tunnel())[0] == 403


def test_public_clients_get_the_mock_mc_no_operator_buttons_and_never_the_secret(pub):
    b = base(pub)
    st, _, body = get(b + "/play/link.js", tunnel())
    cfg = body.decode()
    assert '"mc": "mock"' in cfg and '"liveVoice": false' in cfg and '"operator": false' in cfg
    assert f'"joinUrl": "https://{HOST}/ticket.html"' in cfg
    local = get(b + "/play/link.js")[2].decode()
    assert '"operator": true' in local and '"secretRequired": true' in local
    pages = [get(b + p, h)[2].decode("utf-8", "replace") for p in ("/", "/play/link.js", "/ticket.html", "/phone", "/phone/phone.js", "/play/ticket-hook.js")
             for h in (tunnel(), None)]
    assert all(SECRET not in p and "operator_secret" not in p for p in pages)
    assert get(b + "/play/mc-audio.js", tunnel())[0] == 404 and get(b + "/play/mc-audio.js")[0] == 200


def test_security_headers_on_public_responses_only(pub):
    b = base(pub)
    h = get(b + "/", tunnel())[1]
    assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "no-referrer" and h["x-frame-options"] == "SAMEORIGIN"
    assert "x-content-type-options" not in get(b + "/")[1]


# ---------------------------------------------------------------- operator actions and the live MC
def test_public_clients_cannot_reach_operator_actions_even_with_the_secret(pub):
    b = base(pub)
    for path, body in (("/api/reset", {"force": True}), ("/api/mc/connect", {}), ("/api/mc/disconnect", {})):
        assert post(b + path, body, tunnel(**op()))[0] == 403, path
    assert get(b + "/api/mc/status", tunnel(**op()))[0] == 403
    with pytest.raises((InvalidStatus, InvalidHandshake, ConnectionClosed)):
        with pws(pub, "/ws/mc") as ws:
            ws.send(json.dumps({"t": "hello", "secret": SECRET}))
            ws.recv(timeout=2)
    with pytest.raises((InvalidStatus, InvalidHandshake, ConnectionClosed)):  # take-over is an operator action
        with pws(pub, "/ws/stage?cid=x&take=1") as ws:
            ws.send(hello()); ws.recv(timeout=2)
    assert pub.host.engine.stats["gate_timeouts"] == 0 and pub.host.game_index == 0  # nothing happened


def test_local_operator_actions_need_the_secret_header_and_origin(pub):
    b = base(pub)
    assert post(b + "/api/reset", {"force": True})[0] == 403  # no secret
    assert post(b + "/api/reset", {"force": True}, {"X-KHQS-Operator": "nope"})[0] == 403
    assert post(b + "/api/reset", {"force": True}, {"X-KHQS": "", **op()})[0] == 403  # no custom header
    assert post(b + "/api/reset", {"force": True}, op({"Origin": "http://evil.example"}))[0] == 403
    assert post(b + "/api/reset", {"force": True}, op())[1] == {"ok": True}
    assert pub.host.game_index == 1
    assert get(b + "/api/mc/status")[0] == 403 and get(b + "/api/mc/status", op())[0] == 200


def test_wrong_secrets_lock_the_client_out_and_the_log_never_has_a_secret(pub, caplog):
    caplog.set_level(logging.DEBUG)
    b = base(pub)
    codes = [post(b + "/api/reset", {"force": True}, {"X-KHQS-Operator": f"guess-number-{i}"})[0] for i in range(6)]
    assert codes[:5] == [403] * 5 and codes[5] == 429
    assert post(b + "/api/reset", {"force": True}, op())[0] == 429  # the right secret also waits
    text = caplog.text
    assert SECRET not in text and "guess-number" not in text and "count=" in text
    assert SECRET not in repr(pub.settings) and SECRET not in repr(pub.host.settings)


def test_take_over_needs_the_operator_frame_before_the_hello(pub):
    with pws(pub, "/ws/stage?cid=a", ip="203.0.113.7", headers={}) as primary:
        primary.send(hello()); primary.recv(timeout=3)
        local = f"ws://127.0.0.1:{pub.settings.stage_port}/ws/stage?cid=b&take=1"
        with connect(local, additional_headers={"Origin": f"http://127.0.0.1:{pub.settings.stage_port}"}) as ws:
            ws.send(hello())  # no operator frame first
            assert closed(ws)
        with connect(local, additional_headers={"Origin": f"http://127.0.0.1:{pub.settings.stage_port}"}) as ws:
            ws.send(json.dumps({"type": "khqs.operator", "secret": SECRET}))
            ws.send(hello())
            assert json.loads(ws.recv(timeout=3))["type"] == "snapshot"
            assert closed(primary)  # the operator took the main screen


def operator_ws(srv, secret=SECRET, send_hello=True):
    ws = connect(f"ws://127.0.0.1:{srv.settings.stage_port}/ws/mc", additional_headers={"Origin": f"http://127.0.0.1:{srv.settings.stage_port}"})
    if send_hello:
        ws.send(json.dumps({"t": "hello", "secret": secret}))
    return ws


def live_pub():
    transports = []
    srv = RunningServer(make_settings(public=True, public_host=HOST, operator_secret=SECRET, mc="live", join_grace_s=60.0)).start()
    srv.host.live_mc.factory = lambda: FakeTransport(transports)
    return srv, transports


def test_live_mc_only_from_local_with_secret_and_the_show_turns_private():
    srv, transports = live_pub()
    try:
        b = base(srv)
        assert srv.host.mc is srv.host.mock_mc and srv.host.engine.mc_enabled and not srv.host.engine.voice_input  # the public gets the mock
        with operator_ws(srv, send_hello=False) as nohello:  # a connection without the secret frame is closed (after the 5 s hello wait)
            assert closed(nohello, 8)
        with operator_ws(srv, secret="wrong-secret-wrong-secret") as bad:
            assert closed(bad)
        assert post(b + "/api/mc/connect", {}, op())[1]["error"] == "MC OFFLINE — TRY AGAIN"  # secret ok, but no browser audio socket yet
        with operator_ws(srv) as audio:
            time.sleep(0.2)
            # a public visitor is on the stage: the live MC may not start
            with pws(srv, "/ws/stage?cid=pub1") as visitor:
                visitor.send(hello()); visitor.recv(timeout=3)
                assert "PUBLIC PLAYERS" in post(b + "/api/mc/connect", {}, op())[1]["error"]
            time.sleep(0.3)
            assert srv.host.has_public_clients() is False
            assert post(b + "/api/mc/connect", {}, op())[1] == {"ok": True, "mode": "live"}
            assert srv.host.private_show and srv.host.mc is srv.host.live_mc and srv.host.engine.voice_input
            # the private show: strangers are turned away everywhere
            assert get(b + "/", tunnel())[0] == 503 and get(b + "/ticket.html", tunnel())[0] == 503
            assert post(b + "/api/join", {"name": "Stranger"}, tunnel())[0] == 503
            with pytest.raises((InvalidStatus, InvalidHandshake, ConnectionClosed)):
                with pws(srv, "/ws/stage?cid=late") as ws:
                    ws.send(hello()); ws.recv(timeout=2)
            assert get(b + "/")[0] == 200  # the owner still gets in
            assert post(b + "/api/mc/disconnect", {}, op())[1] == {"ok": True}
            assert not srv.host.private_show and srv.host.mc is srv.host.mock_mc
            assert srv.host.engine.mc_enabled and not srv.host.engine.voice_input and not srv.host.engine.status_from_playback  # back to the mock
            assert get(b + "/", tunnel())[0] == 200
        assert srv.host.live_mc.sessions_opened == 1 and len(transports) == 1
    finally:
        srv.stop()


def test_live_mc_refused_while_a_game_has_players_or_runs():
    srv, _ = live_pub()
    try:
        b = base(srv)
        assert post(b + "/api/join", {"name": "Mina"}, tunnel())[1]["ok"]
        with operator_ws(srv):
            time.sleep(0.2)
            assert "PUBLIC PLAYERS" in post(b + "/api/mc/connect", {}, op())[1]["error"]
        assert srv.host.live_mc.state == "offline"
    finally:
        srv.stop()


# ---------------------------------------------------------------- one game, who may start it
def test_only_the_primary_stage_page_can_start_or_reset(pub):
    b = base(pub)
    assert post(b + "/api/join", {"name": "Mina"}, tunnel())[1]["ok"]
    assert post(b + "/api/start", {}, tunnel())[0] == 403  # no stage page, no client id
    with pws(pub, "/ws/stage?cid=main") as main, pws(pub, "/ws/stage?cid=watcher", ip="203.0.113.6") as watcher:
        main.send(hello()); main.recv(timeout=3)
        watcher.send(hello()); watcher.recv(timeout=3)
        assert pub.host.primary_cid() == "main"
        assert post(b + "/api/start", {}, tunnel(**{"X-KHQS-Cid": "watcher"}))[0] == 403  # a viewer cannot start the show
        assert post(b + "/api/start", {}, tunnel(**{"X-KHQS-Cid": "guess"}))[0] == 403
        assert post(b + "/api/reset", {}, tunnel(**{"X-KHQS-Cid": "watcher"}))[0] == 403
        assert post(b + "/api/start", {}, tunnel(**{"X-KHQS-Cid": "main"}))[1] == {"ok": True}
        assert post(b + "/api/reset", {}, tunnel(**{"X-KHQS-Cid": "main"}))[1] == {"error": "SHOW IS STILL RUNNING"}  # one game at a time
    assert pub.host.game_index == 0


# ---------------------------------------------------------------- limits
def test_join_limit_per_client_address(pub):
    b = base(pub)
    for i, n in enumerate(("A1", "B1")):
        assert post(b + "/api/join", {"name": n}, tunnel("203.0.113.9"))[1].get("ok"), n
    st, body = post(b + "/api/join", {"name": "C1"}, tunnel("203.0.113.9"))
    assert st == 429 and "TOO MANY" in body["error"]
    assert post(b + "/api/join", {"name": "C1"}, tunnel("203.0.113.10"))[1].get("ok")  # another visitor is fine
    assert len(pub.host.engine.players) == 3


def test_start_and_reset_rate_limit(pub):
    b = base(pub)
    codes = [post(b + "/api/start", {}, tunnel("203.0.113.11", **{"X-KHQS-Cid": "nobody"}))[0] for _ in range(8)]
    assert codes[:6] == [403] * 6 and codes[6:] == [429, 429]


def test_socket_budgets_per_address_and_in_total(pub):
    opened = []
    try:
        for i in range(8):
            ws = pws(pub, f"/ws/stage?cid=s{i}", ip="203.0.113.20")
            ws.send(hello()); ws.recv(timeout=3)
            opened.append(ws)
        with pytest.raises((InvalidStatus, InvalidHandshake, ConnectionClosed)):  # the ninth from one address
            with pws(pub, "/ws/stage?cid=s9", ip="203.0.113.20") as extra:
                extra.send(hello()); extra.recv(timeout=2)
        for i in range(4):
            ws = pws(pub, f"/ws/stage?cid=t{i}", ip="203.0.113.21")
            ws.send(hello()); ws.recv(timeout=3)
            opened.append(ws)
        with pytest.raises((InvalidStatus, InvalidHandshake, ConnectionClosed)):  # 12 in total
            with pws(pub, "/ws/stage?cid=t9", ip="203.0.113.22") as over:
                over.send(hello()); over.recv(timeout=2)
    finally:
        for ws in opened:
            ws.close()
    time.sleep(0.5)
    ok = pws(pub, "/ws/stage?cid=again", ip="203.0.113.20")  # the budget was released
    ok.send(hello())
    assert json.loads(ok.recv(timeout=3))["type"] == "snapshot"
    ok.close()


def test_origin_must_match_the_public_host(pub):
    b = base(pub)
    assert post(b + "/api/join", {"name": "Mina"}, tunnel(Origin="https://evil.example"))[0] == 403
    assert post(b + "/api/join", {"name": "Mina"}, tunnel(Origin=f"https://{HOST}"))[1].get("ok")
    with pytest.raises((InvalidStatus, InvalidHandshake, ConnectionClosed)):
        with pws(pub, "/ws/stage?cid=x", headers={"Origin": "https://evil.example"}) as ws:
            ws.send(hello()); ws.recv(timeout=2)


def test_lan_phone_port_keeps_working_in_public_mode(pub):
    st, body = post(f"http://127.0.0.1:{pub.settings.phone_port}/api/join", {"name": "LanPhone"})
    assert st == 200 and body["ok"]


# ---------------------------------------------------------------- caps (GAME_RULES section 11) for public games
def timed(**kw):
    srv = RunningServer(make_settings(public=True, public_host=HOST, operator_secret=SECRET, join_grace_s=60.0, **kw)).start()
    srv.host.caps_interval = 0.05
    return srv


def test_idle_game_resets_and_player_input_keeps_it_alive():
    srv = timed(idle_reset_s=1)
    try:
        b = base(srv)
        cred = post(b + "/api/join", {"name": "Mina"}, tunnel())[1]["credential"]
        with pws(srv, "/ws/phone") as p:
            p.send(json.dumps({"type": "hello", "cred": cred}))
            p.recv(timeout=3)
            for _ in range(8):  # a phone action every 0.3 s keeps the game alive for 2.4 s
                p.send(json.dumps({"type": "action", "id": 1, "action": {"type": "ox", "choice": "O"}}))
                time.sleep(0.3)
            assert srv.host.game_index == 0 and srv.host.engine.players
            time.sleep(1.6)  # then nothing for more than 1 s
        assert srv.host.game_index == 1 and not srv.host.engine.players
    finally:
        srv.stop()


def test_game_age_cap_resets_even_with_input():
    srv = timed(game_cap_s=1, idle_reset_s=999)
    try:
        post(base(srv) + "/api/join", {"name": "Mina"}, tunnel())
        time.sleep(1.5)
        assert srv.host.game_index == 1 and not srv.host.engine.players
    finally:
        srv.stop()
