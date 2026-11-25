"""Stage socket, reconnect race, phone socket, limits, the show API, new game, and the pump."""
import asyncio
import json
import random
import time

import pytest
from websockets.exceptions import ConnectionClosed

from khqs.content.dev_bank import build_dev_bank
from khqs.engine.config import EngineConfig
from khqs.server.host import GameHost
from net import get, hello, post, ws_open
from conftest import make_settings
from fasthost import FastHost


def sbase(srv):
    return f"http://127.0.0.1:{srv.settings.stage_port}"


def stage_ws(srv, cid="tab-1", take=False, role="primary"):
    ws = ws_open(f"ws://127.0.0.1:{srv.settings.stage_port}/ws/stage?cid={cid}{'&take=1' if take else ''}")
    ws.send(hello(role))
    return ws


def recv_all(ws, wait=0.4):
    out = []
    while True:
        try:
            out.append(json.loads(ws.recv(timeout=wait)))
        except (TimeoutError, ConnectionClosed):
            return out


def join(srv, name, port=None):
    st, body = post(f"http://127.0.0.1:{port or srv.settings.stage_port}/api/join", {"name": name})
    assert st == 200 and body.get("ok"), body
    return body


def phone_ws(srv, cred, port=None):
    ws = ws_open(f"ws://127.0.0.1:{port or srv.settings.phone_port}/ws/phone")
    ws.send(json.dumps({"type": "hello", "cred": cred}))
    return ws


def closed(ws, wait=2.0):
    """True if the server closes this socket within `wait` seconds (other messages are drained)."""
    end = time.monotonic() + wait
    while time.monotonic() < end:
        try:
            ws.recv(timeout=max(0.05, end - time.monotonic()))
        except ConnectionClosed:
            return True
        except TimeoutError:
            return False
    return False


# ---------------------------------------------------------------- stage socket
def test_hello_snapshot_then_stream_to_primary_and_viewer_and_ack_closes_a_gate(server):
    join(server, "Mina")
    p = stage_ws(server, "p")
    first = json.loads(p.recv(timeout=3))
    assert first["type"] == "snapshot" and first["data"]["game"]["phase"] == "lobby"
    v = stage_ws(server, "v", role="viewer")
    assert json.loads(v.recv(timeout=3))["type"] == "snapshot"
    assert post(sbase(server) + "/api/start", {})[1] == {"ok": True}
    pm = recv_all(p, 0.5)
    types = [m["type"] for m in pm]
    assert "show.opening" in types and types[0] == "phase.changed"
    gate = next(m for m in pm if m["type"] == "show.opening")
    assert [m["type"] for m in recv_all(v, 0.3)][:2] == ["phase.changed", "show.opening"]
    # a viewer's ack is ignored; the primary's closes the gate and the greeting (mock MC) then plays
    v.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.beat_done", "data": {"gate": gate["gate"]["id"], "sseq": gate["sseq"]}}))
    assert not [m for m in recv_all(p, 0.5) if m["type"] in ("mc.status", "phase.changed")]
    p.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.beat_done", "data": {"gate": gate["gate"]["id"], "sseq": gate["sseq"]}}))
    after = recv_all(p, 1.5)
    assert any(m["type"] == "mc.status" and m["data"]["status"] == "speaking" for m in after)
    assert any(m["type"] == "mc.caption" for m in after)  # the mock MC's greeting went through the caption filter
    assert [m["sseq"] for m in pm + after] == list(range(pm[0]["sseq"], pm[0]["sseq"] + len(pm + after)))


def test_ping_and_need_snapshot_direct_replies_only_to_the_asker(server):
    a, b = stage_ws(server, "a"), stage_ws(server, "b", role="viewer")
    a.recv(timeout=3); b.recv(timeout=3); recv_all(b, 0.3)
    a.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.ping", "data": {"clientTime": 5.0}}))
    pong = json.loads(a.recv(timeout=3))
    assert pong["type"] == "pong" and pong["data"]["clientTime"] == 5.0
    assert recv_all(b, 0.3) == []
    a.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.need_snapshot", "data": {"lastSseq": 0, "receivedSseq": 3}}))
    assert json.loads(a.recv(timeout=3))["type"] == "snapshot"
    assert recv_all(b, 0.3) == []


def test_bad_first_message_closes_the_socket(server):
    ws = ws_open(f"ws://127.0.0.1:{server.settings.stage_port}/ws/stage?cid=x")
    ws.send(json.dumps({"type": "stage.ping", "data": {}}))
    assert closed(ws)
    ws = ws_open(f"ws://127.0.0.1:{server.settings.stage_port}/ws/stage?cid=x")
    ws.send("not json")
    assert closed(ws)


def test_reconnect_race_same_cid_replaces_the_old_socket_and_stays_primary(server):
    old = stage_ws(server, "tab-A")
    old.recv(timeout=3)
    new = stage_ws(server, "tab-A")  # the new page's hello arrives while the old socket is still open
    snap = json.loads(new.recv(timeout=3))
    assert snap["type"] == "snapshot"
    assert closed(old), "the old socket must be closed by the server"
    assert not [m for m in recv_all(new, 0.4) if m["type"] == "error"]  # no primary_taken for the new one
    host = server.host
    assert [c.role for c in host.stage.values()] == ["primary"] and host.engine.primary == next(iter(host.stage))


def test_another_tab_is_a_viewer_and_take_over_is_explicit(server):
    a = stage_ws(server, "tab-A"); a.recv(timeout=3)
    b = stage_ws(server, "tab-B")
    msgs = [json.loads(b.recv(timeout=3)) for _ in range(2)]
    assert [m["type"] for m in msgs] == ["snapshot", "error"] and msgs[1]["data"]["code"] == "primary_taken"
    assert not closed(a, 0.5)  # A keeps the primary seat
    c = stage_ws(server, "tab-B", take=True)  # the operator presses TAKE OVER
    assert json.loads(c.recv(timeout=3))["type"] == "snapshot"
    assert closed(a)
    assert sorted(x.role for x in server.host.stage.values()) == ["primary", "viewer"]


def test_closing_every_stage_socket_does_not_stop_the_game(server):
    join(server, "Mina")
    s = stage_ws(server); s.recv(timeout=3)
    post(sbase(server) + "/api/start", {})
    recv_all(s, 0.3)
    s.close()
    time.sleep(0.3)
    assert server.host.stage == {} and server.host.engine.phase == "opening"
    assert server.host.engine.next_due() is not None  # the opening gate's safety deadline is still ticking


# ---------------------------------------------------------------- phone socket
def test_phone_hello_views_actions_and_connection_state(server):
    s = stage_ws(server); s.recv(timeout=3)
    body = join(server, "Mina", port=server.settings.phone_port)
    seat = body["seat"]
    assert seat == 1
    p = phone_ws(server, body["credential"], port=server.settings.phone_port)
    view = json.loads(p.recv(timeout=3))
    assert view["type"] == "view" and view["view"]["you"]["name"] == "Mina" and view["view"]["screen"] == "waiting"
    assert server.host.engine.players[1].connected is True
    p.send(json.dumps({"type": "action", "id": 7, "action": {"type": "ox", "choice": "O"}}))
    res = next(m for m in recv_all(p, 0.5) if m["type"] == "result")
    assert res == {"type": "result", "id": 7, "ok": False, "error": "not_now"}
    p2 = phone_ws(server, body["credential"])  # a second socket for the same seat (reload)
    json.loads(p2.recv(timeout=3))
    p.close()
    time.sleep(0.3)
    assert not [m for m in recv_all(s, 0.3) if m["type"] == "seat.connection"]  # still connected through the other socket
    p2.close()
    assert [m["data"] for m in recv_all(s, 1.0) if m["type"] == "seat.connection"] == [{"seat": 1, "connected": False}]
    assert server.host.engine.players[1].connected is False


def test_bad_credential_gets_an_error_and_a_close(server):
    ws = phone_ws(server, "nope")
    assert json.loads(ws.recv(timeout=3)) == {"type": "error", "code": "bad_cred"}
    assert closed(ws)


def test_phone_socket_limits(server):
    cred = join(server, "Mina")["credential"]
    big = phone_ws(server, cred); big.recv(timeout=3)
    big.send(json.dumps({"type": "ping", "pad": "x" * 3000}))
    assert closed(big)
    flood = phone_ws(server, cred); flood.recv(timeout=3)
    for _ in range(80):
        try:
            flood.send(json.dumps({"type": "ping"}))
        except ConnectionClosed:
            break
    assert closed(flood, 3.0)
    socks = [phone_ws(server, cred) for _ in range(4)]
    for s in socks:
        json.loads(s.recv(timeout=3))
    fifth = phone_ws(server, cred)
    assert closed(fifth)  # at most 4 sockets per seat
    junk = ws_open(f"ws://127.0.0.1:{server.settings.phone_port}/ws/phone")
    junk.send("{not json")
    assert closed(junk)
    nohello = ws_open(f"ws://127.0.0.1:{server.settings.phone_port}/ws/phone")
    nohello.send(json.dumps({"type": "action", "id": 1, "action": {"type": "buzz"}}))
    assert closed(nohello)


# ---------------------------------------------------------------- API and new game
def test_join_start_errors_and_credential_only_in_the_join_response(server):
    base = sbase(server)
    assert post(base + "/api/start", {})[1] == {"error": "NEED A PLAYER"}
    assert post(base + "/api/join", {"name": ""})[1] == {"error": "TYPE A NAME"}
    a = join(server, "Mina")
    assert post(base + "/api/join", {"name": "mina"})[1] == {"error": "THAT NAME IS TAKEN"}
    join(server, "Junho"); join(server, "Ray")
    assert post(base + "/api/join", {"name": "Zed"})[1] == {"error": "HOUSE FULL"}
    assert post(base + "/api/start", {})[1] == {"ok": True}
    assert post(base + "/api/start", {})[1] == {"error": "SHOW ALREADY STARTED"}
    assert post(base + "/api/join", {"name": "Late"})[1] == {"error": "SHOW IN PROGRESS"}
    rec = server.host.recorder
    blob = json.dumps([rec.stream, rec.snapshots, [v for _, v in rec.views][-1:]], ensure_ascii=False)
    assert a["credential"] not in blob


def test_reset_rules_and_a_new_game_keeps_roles_alternates_sets_and_retires_phones(server):
    base = sbase(server)
    assert post(base + "/api/reset", {})[1] == {"error": "SHOW IS STILL RUNNING"}  # needs `ended` unless forced
    old = join(server, "Mina")
    phone = phone_ws(server, old["credential"]); phone.recv(timeout=3)
    a = stage_ws(server, "A"); json.loads(a.recv(timeout=3))
    b = stage_ws(server, "B"); b.recv(timeout=3); b.recv(timeout=3)
    g0 = server.host.engine.game_id
    assert post(base + "/api/reset", {"force": True})[1] == {"ok": True}
    snap_a = next(m for m in recv_all(a, 0.6) if m["type"] == "snapshot")
    assert snap_a["data"]["game"]["id"] != g0 and snap_a["data"]["game"]["phase"] == "lobby"
    assert snap_a["data"]["seats"][1]["status"] == "vacant"  # the old player is gone
    snap_b = next(m for m in recv_all(b, 0.3) if m["type"] == "snapshot")
    roles = sorted(c.role for c in server.host.stage.values())
    assert roles == ["primary", "viewer"] and server.host.engine.primary == next(c.conn_id for c in server.host.stage.values() if c.role == "primary")
    msgs = recv_all(phone, 1.0)
    assert {"type": "gone"} in msgs and closed(phone)
    assert server.host.game_index == 1 and server.host.engine.content.set_id == "dev-b"  # sets alternate
    stale = phone_ws(server, old["credential"])
    assert json.loads(stale.recv(timeout=3)) == {"type": "error", "code": "bad_cred"}
    assert [m["sseq"] for m in server.host.engine.stream] == [1]  # a fresh stream per game


# ---------------------------------------------------------------- the clock pump
@pytest.mark.slow
def test_pump_runs_a_whole_game_with_no_stage_and_no_players_acting():
    """Tiny windows, real clock, no sockets at all: the pump alone must carry the show to the end."""
    async def main():
        s = make_settings(mock_speed=50.0)
        host = FastHost(s, build_dev_bank(s.media_dir))
        host.start_pump()
        assert host.join("Mina").ok and host.start().ok
        t0 = time.monotonic()
        while host.engine.phase != "ended" and time.monotonic() - t0 < 90:
            await asyncio.sleep(0.1)
        phase, n, stats = host.engine.phase, len(host.engine.stream), host.engine.stats
        await host.stop()
        return phase, n, stats

    phase, n, stats = asyncio.run(main())
    assert phase == "ended" and n > 150
    assert stats["gate_timeouts"] > 0  # no stage ever acked, so every gate closed on its safety deadline


def test_a_joined_player_without_a_phone_socket_is_shown_disconnected_after_the_grace_period():
    from khqs.server.runner import RunningServer
    srv = RunningServer(make_settings(join_grace_s=0.4)).start()
    try:
        s = stage_ws(srv); s.recv(timeout=3)
        join(srv, "Mina")
        assert srv.host.engine.players[1].connected is True
        ev = [m["data"] for m in recv_all(s, 1.2) if m["type"] == "seat.connection"]
        assert ev == [{"seat": 1, "connected": False}]
        p = phone_ws(srv, [c for c in [srv.host.engine.players[1].credential]][0]); p.recv(timeout=3)
        assert [m["data"] for m in recv_all(s, 0.5) if m["type"] == "seat.connection"] == [{"seat": 1, "connected": True}]
    finally:
        srv.stop()
