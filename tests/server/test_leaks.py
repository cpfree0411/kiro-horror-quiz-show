"""Regression tests for the leak classes the P6 soak looked for and found."""
import asyncio
import json
import os
import socket
import time

import pytest
from websockets.sync.client import connect

from khqs.server.host import Conn, QUEUE_MAX
from khqs.server.runner import RunningServer
from khqs.server.stats import collect, descriptors
from net import hello, post
from settings_util import make_settings


def test_closing_a_socket_with_a_full_send_queue_does_not_leave_its_writer_task_behind():
    class StuckWs:  # the peer never reads: the first send never finishes
        async def send_text(self, text):
            await asyncio.sleep(3600)

        async def close(self, code=1000):
            return None

    async def main():
        c = Conn(StuckWs(), "stage")
        for i in range(QUEUE_MAX + 20):
            c.send({"n": i})  # fills the queue; the overflow closes the socket (1013)
        await asyncio.sleep(0.05)
        assert c.closed
        await asyncio.sleep(0.05)
        return c.task.done()
    assert asyncio.run(main()), "the writer task of a closed, backed-up socket must end"


def test_a_phone_that_reloads_within_the_grace_time_is_never_announced_as_disconnected():
    srv = RunningServer(make_settings(disconnect_grace_s=0.6)).start()
    try:
        b = f"http://127.0.0.1:{srv.settings.stage_port}"
        cred = post(b + "/api/join", {"name": "Mina"})[1]["credential"]
        url = f"ws://127.0.0.1:{srv.settings.stage_port}/ws/phone"
        for _ in range(20):  # a reload storm
            with connect(url) as ws:
                ws.send(json.dumps({"type": "hello", "cred": cred}))
                ws.recv(timeout=2)
            time.sleep(0.05)
        time.sleep(0.2)
        assert not [m for m in srv.host.engine.stream if m["type"] == "seat.connection"]  # the stage heard nothing
        assert srv.host._gone  # one pending announcement, not twenty
        time.sleep(1.0)
        ev = [m["data"] for m in srv.host.engine.stream if m["type"] == "seat.connection"]
        assert ev == [{"seat": 1, "connected": False}]  # a real drop is announced once, after the grace
        assert not srv.host._gone
        with connect(url) as ws:
            ws.send(json.dumps({"type": "hello", "cred": cred}))
            ws.recv(timeout=2)
            time.sleep(0.2)
        assert [m["data"] for m in srv.host.engine.stream if m["type"] == "seat.connection"][-1] == {"seat": 1, "connected": True}
    finally:
        srv.stop()


def test_reconnect_storm_returns_descriptors_tasks_timers_and_tables_to_baseline():
    srv = RunningServer(make_settings()).start()
    try:
        port = srv.settings.stage_port
        cred = post(f"http://127.0.0.1:{port}/api/join", {"name": "Mina"})[1]["credential"]
        time.sleep(0.3)
        base = collect(srv)
        for i in range(120):
            kind = i % 4
            sock = socket.create_connection(("127.0.0.1", port))
            if kind in (0, 1):
                ws = connect(f"ws://127.0.0.1:{port}/ws/phone", sock=sock)
                ws.send(json.dumps({"type": "hello", "cred": cred if kind == 0 else "bad"}))
            else:
                ws = connect(f"ws://127.0.0.1:{port}/ws/stage?cid=main{'&take=1' if kind == 3 else ''}", sock=sock)
                ws.send(hello("primary" if kind == 2 else "viewer"))
            try:
                ws.recv(timeout=2)
            except Exception:
                pass
            if i % 2:
                sock.shutdown(socket.SHUT_RDWR)  # abrupt: no close frame
            ws.close()
            sock.close()
        time.sleep(1.0)
        end = collect(srv)
        for k in ("stage_socks", "phone_socks", "mc_pending"):
            assert end[k] == 0, (k, end)
        assert end["tasks"] <= base["tasks"] + 1 and end["timers"] <= base["timers"] + 1, (base, end)
        fds, _ = descriptors()
        assert end["fds"] <= base["fds"] + 2, (base, end)
        assert len(srv.host.stage) == 0 and len(srv.host._gone) <= 1
    finally:
        srv.stop()


def test_a_finished_game_can_be_garbage_collected_after_new_show():
    """Found by the 30-game soak: a join-grace timer per player kept every finished game's engine alive (timers +2 per game)."""
    import gc
    import weakref

    from khqs.content.dev_bank import build_dev_bank
    from khqs.server.host import GameHost

    async def main():
        s = make_settings(record=False, join_grace_s=600.0)
        host = GameHost(s, build_dev_bank(s.media_dir))
        host.start_pump()
        for name in ("Mina", "Junho", "Ray"):
            assert host.join(name).ok
        assert len(host._grace) == 3
        old = weakref.ref(host.engine)
        loop = asyncio.get_running_loop()
        before = len([h for h in loop._scheduled if not h.cancelled()])
        host.reset(force=True)
        await asyncio.sleep(0.05)
        gc.collect()
        after = len([h for h in loop._scheduled if not h.cancelled()])
        alive = old() is not None
        await host.stop()
        return alive, before, after, len(host._grace)

    alive, before, after, grace = asyncio.run(main())
    assert not alive, "the old game's engine is still referenced after NEW SHOW"
    assert after < before and grace == 0
