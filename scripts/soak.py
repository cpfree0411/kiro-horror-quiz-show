"""Soak and robustness runs against the real server with real sockets (no browser, no API, mock MC).

  scripts/soak.py games 30            30 back-to-back games through NEW SHOW (short windows, a stage client that acks gates)
  scripts/soak.py storm               phone and stage reconnect storms
  scripts/soak.py idle 3600 [public]  an idle server for N seconds, sampled every 60 s (optionally in public mode)
Each prints a table (RSS, descriptors, sockets, threads, asyncio tasks, pending timers, allocated blocks, host tables)
and writes JSON lines to $KHQS_SOAK_OUT (default /srv/workdata/build-cache/khqs-evidence/p6/soak_<mode>.jsonl).
"""
import json
import os
import random
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "server"), str(REPO / "tests" / "server"), str(REPO / "tests")]

from websockets.exceptions import ConnectionClosed  # noqa: E402
from websockets.sync.client import connect  # noqa: E402

from khqs.engine.config import EngineConfig  # noqa: E402
from khqs.engine.core import Engine  # noqa: E402
from khqs.server.host import GameHost  # noqa: E402
from khqs.server.runner import RunningServer  # noqa: E402
from khqs.server.settings import Settings  # noqa: E402
from khqs.server.stats import collect  # noqa: E402
from settings_util import free_port  # noqa: E402

OUT_DIR = Path(os.environ.get("KHQS_SOAK_OUT_DIR", "/srv/workdata/build-cache/khqs-evidence/p6"))
COLUMNS = ["rss_kb", "fds", "sockets", "threads", "tasks", "timers", "blocks", "stage_socks", "phone_socks", "mc_pending", "stream_len", "limiter_conn"]


class FastHost(GameHost):
    """Real host, tiny windows: a whole game in seconds (the stage client acks every gate at once)."""

    def _new_engine(self):
        cfg = EngineConfig(ox_answer_ms=150, betrayal_input_ms=100, prompt_failsafe_ms=600, reading_failsafe_ms=800, buzzer_answer_ms=300,
                           buzzer_open_ms=150, music_open_ms=150, media_interrupt_wait_ms=100, media_watchdog_extra_ms=100, final_bet_ms=150,
                           final_answer_ms=150, gate_grace_ms=300, gate_timeouts={k: 60 for k in EngineConfig().gate_timeouts})
        return Engine(self.bank, self.clock, random.Random(self.game_index + 1), cfg, game_index=self.game_index, **self.mc.engine_flags())


def api(base, path, body=None, headers=None):
    h = {"content-type": "application/json", "X-KHQS": "1", **(headers or {})}
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


class StageClient(threading.Thread):
    """A stage page without the page: acks every gate, finishes music clips at once, records the end of each game."""

    def __init__(self, port, cid="soak-stage"):
        super().__init__(daemon=True)
        self.url, self.cid, self.stop = f"ws://127.0.0.1:{port}/ws/stage?cid={cid}", cid, False
        self.ended = threading.Event()
        self.lobby = threading.Event()
        self.games_ended = 0
        self.last_sseq = None
        self.error = None

    def run(self):
        try:
            with connect(self.url, open_timeout=10, max_size=None) as ws:
                ws.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.hello", "data": {
                    "role": "primary", "stageVersion": "soak", "lastSseq": None, "clientTime": 1.0, "beats": {}}}))
                while not self.stop:
                    try:
                        m = json.loads(ws.recv(timeout=1))
                    except TimeoutError:
                        continue
                    t = m.get("type")
                    if t == "snapshot":
                        self.last_sseq = m["sseq"]
                        if m["data"]["game"]["phase"] == "lobby":
                            self.lobby.set()
                        g = m["data"].get("openGate")
                        if g:
                            ws.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.beat_done", "data": {"gate": g["id"], "sseq": int(g["id"][2:]), "skipped": True}}))
                        continue
                    if "sseq" in m:
                        self.last_sseq = m["sseq"]
                    if m.get("gate"):
                        ws.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.beat_done", "data": {"gate": m["gate"]["id"], "sseq": m["sseq"]}}))
                    if t == "av.play":
                        d = m["data"]
                        ws.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.media_ended", "data": {
                            "assetId": d["assetId"], "level": d["level"], "reason": "ended", "positionSec": d["endSec"]}}))
                    if t == "game.ended":
                        self.games_ended += 1
                        self.ended.set()
        except (ConnectionClosed, OSError) as e:
            self.error = repr(e)


class PhoneBot(threading.Thread):
    def __init__(self, port, cred, name):
        super().__init__(daemon=True)
        self.url, self.cred, self.name, self.stop = f"ws://127.0.0.1:{port}/ws/phone", cred, name, False

    def run(self):
        try:
            with connect(self.url, open_timeout=10) as ws:
                ws.send(json.dumps({"type": "hello", "cred": self.cred}))
                n = 0
                seen = None
                while not self.stop:
                    try:
                        m = json.loads(ws.recv(timeout=1))
                    except TimeoutError:
                        continue
                    if m.get("type") in ("gone", "error"):
                        return
                    v = m.get("view")
                    if not v or v["screen"] == seen:
                        continue
                    seen = v["screen"]
                    a = {"ox": {"type": "ox", "choice": "O"}, "buzzer": {"type": "buzz"}, "answer_text": {"type": "text_answer", "text": "mirror"},
                         "bet": {"type": "bet", "amount": 0}, "final_choice": {"type": "final_choice", "choice": "B"},
                         "betrayal_reason": {"type": "betrayal_reason", "reason": "hunch"}, "betrayal_decision": {"type": "betrayal_decision", "switch": False}}.get(v["screen"])
                    if a:
                        n += 1
                        ws.send(json.dumps({"type": "action", "id": n, "action": a}))
        except (ConnectionClosed, OSError):
            return


def proc_status(pid):
    fields = {}
    with open(f"/proc/{pid}/status", encoding="ascii") as f:
        for line in f:
            k, _, v = line.partition(":")
            if k in ("VmRSS", "Threads"):
                fields[k] = int(v.split()[0])
    fds = socks = 0
    for fd in os.listdir(f"/proc/{pid}/fd"):
        try:
            t = os.readlink(f"/proc/{pid}/fd/{fd}")
        except OSError:
            continue
        fds += 1
        socks += t.startswith("socket:")
    return {"rss_kb": fields["VmRSS"], "threads": fields["Threads"], "fds": fds, "sockets": socks}


class ServerProc:
    """The server in its own process, so client sockets and threads never pollute its numbers."""

    def __init__(self, settings_kw=None, fast=True):
        import subprocess
        self.settings = Settings(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True, seed=1,
                                 mock_speed=50.0, join_grace_s=600.0, diag=True, **(settings_kw or {})).validate()
        args = json.dumps({"stage_port": self.settings.stage_port, "phone_port": self.settings.phone_port, "fast": fast, **(settings_kw or {})})
        self.p = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "serve", args], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        end = time.time() + 20
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", self.settings.phone_port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise SystemExit("server process did not start")
        self.pid = self.p.pid
        secret = (settings_kw or {}).get("operator_secret")
        self.auth = {"X-KHQS-Operator": secret} if secret else {}

    def diag(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.settings.stage_port}/api/diag", headers=self.auth)
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(10)
        except Exception:
            self.p.kill()


def sample(srv, label, rows, out):
    s = srv.diag()  # in-loop numbers: tasks, timers, tables, allocated blocks
    s.update(proc_status(srv.pid))  # the process as the OS sees it (overrides the in-process view)
    s["label"] = label
    s["t"] = round(time.time())
    rows.append(s)
    out.write(json.dumps(s) + "\n")
    out.flush()
    return s


def table(rows):
    print(f"{'label':>14} " + " ".join(f"{c[:11]:>11}" for c in COLUMNS))
    for r in rows:
        print(f"{r['label']:>14} " + " ".join(f"{str(r.get(c, '')):>11}" for c in COLUMNS))


def summary(rows, base_label):
    base = next(r for r in rows if r["label"] == base_label)
    last = rows[-1]
    print(f"\nchange from {base_label} to {last['label']}:")
    for c in COLUMNS:
        if c in base and c in last:
            d = last[c] - base[c]
            print(f"  {c:>14}: {base[c]:>10} -> {last[c]:>10}  ({d:+d})")


def start_server(settings_kw=None, fast=True):
    return ServerProc(settings_kw, fast)


def play_one_game(srv, stage, players):
    base = f"http://127.0.0.1:{srv.settings.stage_port}"
    phone_base = srv.settings.phone_port
    stage.ended.clear()
    stage.lobby.clear()
    bots = []
    for i in range(players):
        r = api(base, "/api/join", {"name": f"P{i}"})
        assert r.get("ok"), r
        bots.append(PhoneBot(srv.settings.phone_port, r["credential"], f"P{i}"))
        bots[-1].start()
    time.sleep(0.3)
    assert api(base, "/api/start", {}).get("ok")
    if not stage.ended.wait(180):
        raise SystemExit("game did not end")
    time.sleep(0.4)
    for b in bots:
        b.stop = True
    assert api(base, "/api/reset", {}).get("ok")  # NEW SHOW
    assert stage.lobby.wait(10)
    for b in bots:
        b.join(5)


def mode_games(n):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    srv = start_server()
    stage = StageClient(srv.settings.stage_port)
    stage.start()
    t0 = time.time()
    with (OUT_DIR / "soak_games.jsonl").open("w") as out:
        sample(srv, "start", rows, out)
        for g in range(1, n + 1):
            play_one_game(srv, stage, players=1 + g % 3)
            if g in (1, 2) or g % 5 == 0 or g == n:
                sample(srv, f"game {g}", rows, out)
        stage.stop = True
        time.sleep(1.5)
        sample(srv, "stage closed", rows, out)
        time.sleep(3)
        sample(srv, "final", rows, out)
    table(rows)
    summary(rows, "game 2")
    print(f"\n{n} games in {time.time() - t0:.0f} s; games ended seen by the stage client: {stage.games_ended}; game_index={rows[-1]['game_index']}")
    srv.stop()


def mode_storm():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    srv = start_server()
    base = f"http://127.0.0.1:{srv.settings.stage_port}"
    rng = random.Random(7)
    r = api(base, "/api/join", {"name": "Storm"})
    cred = r["credential"]
    with (OUT_DIR / "soak_storm.jsonl").open("w") as out:
        sample(srv, "baseline", rows, out)
        for rnd in (1, 2, 3):
            # 1) phone reload storm: open, hello, sometimes act, then close politely, abruptly, or never say anything
            for i in range(600):
                try:
                    kind = rng.choice(["polite", "abrupt", "silent", "badcred", "junk"])
                    if kind == "abrupt":
                        sock = socket.create_connection(("127.0.0.1", srv.settings.stage_port))
                        ws = connect(f"ws://127.0.0.1:{srv.settings.stage_port}/ws/phone", sock=sock)
                    else:
                        ws = connect(f"ws://127.0.0.1:{srv.settings.stage_port}/ws/phone")
                    if kind in ("polite", "abrupt"):
                        ws.send(json.dumps({"type": "hello", "cred": cred}))
                        ws.recv(timeout=2)
                        ws.send(json.dumps({"type": "action", "id": 1, "action": {"type": "ox", "choice": "O"}}))
                    elif kind == "badcred":
                        ws.send(json.dumps({"type": "hello", "cred": "nope"}))
                    elif kind == "junk":
                        ws.send("{not json")
                    if kind == "abrupt":
                        sock.shutdown(socket.SHUT_RDWR)
                        sock.close()
                    else:
                        ws.close()
                except Exception:
                    pass
            time.sleep(1.5)
            sample(srv, f"r{rnd} phones", rows, out)
            # 2) stage reconnect storm: the same client id reconnecting (the reconnect race), viewers, abrupt closes
            for i in range(300):
                try:
                    kind = rng.choice(["same", "viewer", "abrupt", "take"])
                    sock = socket.create_connection(("127.0.0.1", srv.settings.stage_port))
                    ws = connect(f"ws://127.0.0.1:{srv.settings.stage_port}/ws/stage?cid={'main' if kind != 'viewer' else f'v{i}'}" + ("&take=1" if kind == "take" else ""), sock=sock)
                    ws.send(json.dumps({"proto": "khqs.stage/1", "type": "stage.hello", "data": {
                        "role": "viewer" if kind == "viewer" else "primary", "stageVersion": "s", "lastSseq": None, "clientTime": 1.0, "beats": {}}}))
                    ws.recv(timeout=2)
                    if kind == "abrupt":
                        sock.shutdown(socket.SHUT_RDWR)
                        sock.close()
                    else:
                        ws.close()
                except Exception:
                    pass
            time.sleep(1.5)
            sample(srv, f"r{rnd} stage", rows, out)
            # 3) HTTP churn
            for i in range(500):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{srv.settings.stage_port}/stage.js", timeout=5).read()
                except Exception:
                    pass
            time.sleep(1.5)
            sample(srv, f"r{rnd} http", rows, out)
        time.sleep(3)
        sample(srv, "final", rows, out)
    table(rows)
    summary(rows, "r1 http")
    srv.stop()


def mode_idle(seconds, public=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    extra = dict(public=True, public_host="demo.example.com", operator_secret="soak-operator-secret-0123456789") if public else {}
    srv = ServerProc(extra, fast=False)
    t0 = time.time()
    with (OUT_DIR / ("soak_idle_public.jsonl" if public else "soak_idle.jsonl")).open("w") as out:
        sample(srv, "t=0", rows, out)
        n = 0
        while time.time() - t0 < seconds:
            time.sleep(min(60, seconds - (time.time() - t0)))
            n += 1
            sample(srv, f"t={int(time.time() - t0)}s", rows, out)
    table(rows[:3] + rows[-3:])
    summary(rows, "t=0")
    srv.stop()


def mode_serve(args):
    """Child process: the real server, optionally with short windows, diagnostics on."""
    import asyncio
    from khqs.server.runner import serve
    a = json.loads(args)
    fast = a.pop("fast")
    ports = dict(stage_port=a.pop("stage_port"), phone_port=a.pop("phone_port"))
    settings = Settings(phone_host="127.0.0.1", allow_loopback_phone=True, seed=1, mock_speed=50.0 if fast else 1.0, join_grace_s=600.0, diag=True,
                        **ports, **a).validate()
    asyncio.run(serve(settings, host_factory=FastHost if fast else GameHost))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "games"
    if mode == "serve":
        mode_serve(sys.argv[2])
    elif mode == "games":
        mode_games(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif mode == "storm":
        mode_storm()
    elif mode == "idle":
        mode_idle(int(sys.argv[2]) if len(sys.argv) > 2 else 3600, public=len(sys.argv) > 3 and sys.argv[3] == "public")
    else:
        raise SystemExit(__doc__)
