import asyncio
import hmac
import json
import stat
import subprocess
import sys
import urllib.request
from contextlib import contextmanager
from threading import Event

import pytest

from khqs.clock import FakeClock
from khqs.server import visit_log
from khqs.server.runner import RunningServer
from khqs.server.settings import REPO, Settings, SettingsError
from fasthost import FastHost
from net import get, hello, post
from settings_util import make_settings
from test_public_mode import HOST, SECRET, base, lobby_game, op, pws, tunnel

ADDRESS = "203.0.113.5"
AGENT = "Mozilla/5.0 (X11; Linux x86_64) UniquelyIdentifiable-UA"
PERSON = "PvtPlayer7"
ANSWER = "PrivateTypedAnswer"
SALT = b"test-only-secret-salt-bytes-2026"
CID = "never-store-this-stage-cid"
PUB_ENV = {"KHQS_PUBLIC": "1", "KHQS_PUBLIC_HOST": HOST, "KHQS_OPERATOR_SECRET": SECRET}


def headers(**extra):
    return tunnel(**{"CF-IPCountry": "KR", "User-Agent": AGENT, "X-Forwarded-For": "203.0.113.99", **extra})


@pytest.fixture
def visit_files(tmp_path):
    salt = tmp_path / "visits.key"
    salt.write_bytes(SALT)
    return tmp_path / "private" / "visits.jsonl", salt


@contextmanager
def demo(visit_files=None, *, public=True, **kw):
    clock = FakeClock()
    if visit_files is not None:
        kw.update(visit_log=visit_files[0], visit_salt_file=visit_files[1])
    settings = make_settings(public=public, public_host=HOST, operator_secret=SECRET, mock_speed=0.05, **kw)
    srv = RunningServer(settings, lambda s, bank: FastHost(s, bank, clock)).start()
    try:
        yield srv, clock
    finally:
        srv.stop()


def in_server(srv, call):
    async def invoke():
        return call()

    return asyncio.run_coroutine_threadsafe(invoke(), srv.holder["loop"]).result(timeout=3)


def advance_to(srv, clock, phase):
    async def advance():
        eng = srv.host.engine
        for _ in range(500):
            if eng.phase == phase:
                return
            due = eng.next_due()
            assert due is not None, eng.phase
            clock.advance(max(0, due - clock.now_ms()))
            srv.host.run(eng.poll)
            await asyncio.sleep(0)
        pytest.fail(f"stuck in {eng.phase}, waiting for {phase}")

    asyncio.run_coroutine_threadsafe(advance(), srv.holder["loop"]).result(timeout=3)


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_disabled_by_default_and_in_local_mode(tmp_path, visit_files):
    assert Settings.from_env(PUB_ENV).visit_log is None
    path, salt = visit_files
    with demo() as (srv, _):
        assert get(base(srv) + "/", headers())[0] == 200
        assert srv.host.visit_log is None
    with demo((path, tmp_path / "missing-key"), public=False) as (srv, _):
        assert get(base(srv) + "/")[0] == 200
        assert srv.host.visit_log is None and not path.exists()
    assert Settings.from_env({**PUB_ENV, "KHQS_VISIT_SALT_FILE": str(salt)}).visit_log is None


def test_public_visit_log_needs_readable_separate_salt(visit_files):
    path, salt = visit_files
    env = {**PUB_ENV, "KHQS_VISIT_LOG": str(path)}
    with pytest.raises(SettingsError, match="needs KHQS_VISIT_SALT_FILE"):
        Settings.from_env(env)
    for invalid in (path, salt.parent, salt.with_name("missing")):
        with pytest.raises(SettingsError, match="separate files|readable regular file"):
            Settings.from_env({**env, "KHQS_VISIT_SALT_FILE": str(invalid)})
    salt.write_bytes(b"short")
    with pytest.raises(SettingsError, match="at least 16 bytes"):
        Settings.from_env({**env, "KHQS_VISIT_SALT_FILE": str(salt)})
    salt.write_bytes(SALT)
    with pytest.raises(SettingsError, match="outside the served directories"):
        Settings.from_env({**env, "KHQS_VISIT_LOG": str(REPO / "stage" / "assets" / "visits.json"),
                           "KHQS_VISIT_SALT_FILE": str(salt)})
    assert Settings.from_env({**env, "KHQS_VISIT_SALT_FILE": str(salt)}).read_visit_key() == SALT


@pytest.mark.parametrize(("ua", "expected"), [
    ("Mozilla/5.0 (Linux; Android 14; Mobile)", "mobile"), ("Mozilla/5.0 (iPad)", "tablet"),
    ("Mozilla/5.0 (Linux; Android 14)", "tablet"), (AGENT, "desktop"), ("", "other"),
    *[(ua, "bot") for ua in ("Googlebot/2.1", "curl/8.1", "Python-urllib/3.12", "Wget/1.25", "HeadlessChrome")],
])
def test_coarse_device(ua, expected):
    assert visit_log.device(ua) == expected


def test_page_views_use_trusted_address_and_never_log_local_or_lan(visit_files):
    path, salt = visit_files
    with demo(visit_files) as (srv, _):
        b = base(srv)
        assert get(b + "/")[0] == 200
        assert get(b + "/", {"Host": HOST})[0] == 200  # no forwarded client address
        assert get(b + "/not-a-page", headers())[0] == 404
        assert get(b + "/stage.js", headers())[0] == 200
        with urllib.request.urlopen(urllib.request.Request(b + "/", headers=headers(), method="HEAD")) as response:
            assert response.status == 200
        assert get(f"http://127.0.0.1:{srv.settings.phone_port}/ticket.html", headers())[0] == 200
        for url in ("/", "/index.html", "/ticket.html"):
            assert get(b + url, headers())[0] == 200
        assert get(b + "/phone?pad=1", headers(**{"CF-IPCountry": "untrusted arbitrary text"}))[0] == 200
        assert get(b + "/", headers(**{"CF-Connecting-IP": "203.0.113.6", "User-Agent": "curl/1"}))[0] == 200
    events = rows(path)
    assert [r["ev"] for r in events] == ["stage_view", "stage_view", "ticket_view", "phone_view", "stage_view"]
    vid = hmac.digest(SALT, ADDRESS.encode(), "sha256").hex()[:12]
    assert {r["vid"] for r in events[:4]} == {vid} and events[-1]["vid"] != vid
    assert all(r["t"] == "2025-10-24T10:00:00+00:00" for r in events)
    assert [r["cc"] for r in events] == ["KR", "KR", "KR", None, "KR"]
    assert [r["dev"] for r in events] == ["desktop"] * 4 + ["bot"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    salt.write_bytes(b"another-test-only-secret-salt")
    with demo(visit_files) as (srv, _):
        assert get(base(srv) + "/", headers())[0] == 200
    assert rows(path)[:-1] == events and rows(path)[-1]["vid"] != vid


def receive_until(ws, matches):
    while True:
        message = json.loads(ws.recv(timeout=3))
        if matches(message):
            return message


def phone_action(phone, action):
    phone.send(json.dumps({"type": "action", "id": "private-action-id", "action": action}))
    assert receive_until(phone, lambda msg: msg["type"] == "result")["ok"]


def test_public_game_milestones_and_privacy(visit_files, caplog):
    caplog.set_level("INFO", logger="khqs.server")
    path, _ = visit_files
    action = headers(**{"X-KHQS-Cid": CID})
    with demo(visit_files) as (srv, clock):
        b = base(srv)
        sock_headers = {"CF-IPCountry": "KR", "User-Agent": AGENT}
        with pws(srv, f"/ws/stage?cid={CID}", headers=sock_headers) as stage:
            stage.send(hello())
            assert lobby_game(stage)
            assert post(b + "/api/start", {}, action)[1] == {"error": "NEED A PLAYER"}
            assert post(b + "/api/reset", {}, action)[1] == {"error": "SHOW IS STILL RUNNING"}
            _, player = post(b + "/api/join", {"name": PERSON}, action)
            assert player["ok"]
            other = headers(**{"CF-Connecting-IP": "203.0.113.6"})
            assert post(b + "/api/join", {"name": "PhoneVisitor"}, other)[1]["ok"]
            assert post(b + "/api/join", {"name": "LocalPlayer"})[1]["ok"]
            assert post(b + "/api/start", {}, action)[1]["ok"]
            start_ms = clock.now_ms()
            with pws(srv, "/ws/phone") as phone:
                phone.send(json.dumps({"type": "hello", "cred": player["credential"]}))
                assert json.loads(phone.recv(timeout=3))["type"] == "view"
                advance_to(srv, clock, "buzzer.reading")
                phone_action(phone, {"type": "buzz"})
                phone_action(phone, {"type": "text_answer", "text": ANSWER})
                advance_to(srv, clock, "ended")
                receive_until(phone, lambda msg: msg["type"] == "view" and msg["view"]["screen"] == "done")
                receive_until(stage, lambda msg: msg["type"] == "game.ended")
            play_secs = (clock.now_ms() - start_ms) // 1000
            assert post(b + "/api/reset", {}, action)[1]["ok"]
            assert post(b + "/api/join", {"name": "RestartGuest"}, headers())[1]["ok"]
            assert post(b + "/api/restart", {}, action)[1]["ok"]
            assert post(b + "/api/reset", {"force": True}, op())[1]["ok"]
    events = rows(path)
    fields = [{k: v for k, v in r.items() if k not in ("t", "vid", "dev", "cc")} for r in events]
    assert fields == [
        {"ev": "stage_open", "role": "primary"},
        {"ev": "join", "players": 1, "via": "pad"},
        {"ev": "join", "players": 2, "via": "phone"},
        {"ev": "start", "players": 3},
        *[{"ev": "act", "act": act} for act in (1, 2, 3)],
        {"ev": "end", "players": 3, "secs": play_secs},
        {"ev": "new_show"},
        {"ev": "join", "players": 1, "via": "phone"},
        {"ev": "restart", "by": "primary", "phase": "lobby", "players": 1},
        {"ev": "stage_close", "role": "primary", "secs": play_secs},
    ]
    assert play_secs > 0 and events[2]["vid"] != events[0]["vid"]
    assert {event["vid"] for event in events[:2] + events[3:]} == {events[0]["vid"]}
    raw = path.read_bytes()
    for private in (ADDRESS, "203.0.113.6", "203.0.113.99", AGENT, PERSON, "LocalPlayer", ANSWER, CID, SECRET,
                    player["credential"], SALT.decode()):
        assert private.encode() not in raw and private not in caplog.text
    assert events[0]["vid"] not in caplog.text


@pytest.mark.parametrize(("setting", "reason"), [("idle_reset_s", "idle"), ("game_cap_s", "cap")])
def test_automatic_reset_keeps_public_attribution_after_disconnect(visit_files, setting, reason):
    path, _ = visit_files
    with demo(visit_files, **{setting: 1}) as (srv, clock):
        assert post(base(srv) + "/api/join", {"name": PERSON}, headers())[1]["ok"]
        in_server(srv, lambda: clock.advance(1000))
        # No public stage or phone is connected when the caps loop resets the lobby.
        async def wait_reset():
            while srv.host.game_index == 0:
                await asyncio.sleep(0.01)

        asyncio.run_coroutine_threadsafe(wait_reset(), srv.holder["loop"]).result(timeout=3)
    join, reset = rows(path)
    expected = {k: v for k, v in join.items() if k != "via"}
    assert reset == dict(expected, ev="auto_reset", reason=reason, phase="lobby", t="2025-10-24T10:00:01+00:00")


def test_size_limit_stops_once(visit_files, caplog):
    path, _ = visit_files
    path.parent.mkdir(mode=0o700)
    path.touch(mode=0o600)
    with path.open("rb+") as out:
        out.truncate(visit_log.MAX_BYTES - 1)
    with demo(visit_files) as (srv, _):
        for _ in range(3):
            assert get(base(srv) + "/", headers())[0] == 200
    assert path.stat().st_size == visit_log.MAX_BYTES - 1
    assert caplog.text.count("visit log stopped at the size limit") == 1


def test_slow_failing_write_does_not_hold_requests(visit_files, monkeypatch, caplog):
    writing, release, failed = Event(), Event(), Event()
    original = visit_log.os.fdopen

    class SlowFailure:
        def __init__(self, file):
            self.file = file

        def fileno(self):
            return self.file.fileno()

        def write(self, line):
            writing.set()
            release.wait(timeout=5)
            failed.set()
            raise OSError("private storage error detail")

    @contextmanager
    def fdopen(fd, mode, **kw):
        with original(fd, mode, **kw) as file:
            yield SlowFailure(file) if mode == "a" else file

    monkeypatch.setattr(visit_log.os, "fdopen", fdopen)
    with demo(visit_files) as (srv, _):
        try:
            assert get(base(srv) + "/", headers())[0] == 200
            assert writing.wait(timeout=2)
            assert post(base(srv) + "/api/join", {"name": PERSON}, headers())[1]["ok"]
            assert not failed.is_set()
        finally:
            release.set()
        assert get(base(srv) + "/", headers())[0] == 200
    assert caplog.text.count("visit log stopped after a storage error") == 1
    assert "private storage error detail" not in caplog.text


def test_summary_and_timeline(tmp_path):
    path = tmp_path / "fixture.jsonl"
    a, b, bot = "a" * 12, "b" * 12, "c" * 12
    event = {"cc": "KR", "dev": "mobile"}
    before, after = "2026-11-27T14:59:59+00:00", "2026-11-27T15:00:00+00:00"
    fixture = [
        dict(event, t=after, vid=a, ev="end", players=1, secs=20),
        dict(event, t=before, vid=a, ev="stage_view"),
        dict(event, t=after, vid=b, ev="ticket_view", cc="US"),
        dict(event, t=before, vid=a, ev="start", players=1),
        dict(event, t=before, vid=a, ev="join", via="pad", players=1),
        dict(event, t=after, vid=a, ev="act", act=3, other_field="never-print-this"),
        dict(event, t=after, vid=bot, ev="stage_view", dev="bot"),
        dict(event, t=after, vid=b, ev="restart", cc="US", by="viewer", phase="ended", players=1),
        dict(event, t=after, vid=b, ev="auto_reset", cc="US", reason="idle", phase="lobby", players=1),
    ]
    path.write_text("\n".join(map(json.dumps, fixture)) + '\n{"t":', encoding="utf-8")

    def cli(*args):
        return subprocess.check_output([sys.executable, REPO / "scripts/visits.py", path, *args], text=True)

    daily = cli()
    assert "2026-11-27 visitors=1 stage_views=1 ticket_views=0 joins=1 started=1" in daily
    assert "2026-11-28 visitors=2 stage_views=0 ticket_views=1 joins=0 started=0 highest_act=3 finished=1" in daily
    assert "Total visitors=2 stage_views=1 ticket_views=1 joins=1 started=1 highest_act=3 finished=1 " \
           "restarts=1 auto_resets=1 bot_visitors=1 bot_events=1" in daily
    assert "\nKR 1\nUS 1\n" in daily
    timeline = cli("--timeline", "--exclude-vid", b, bot)
    assert [l.split()[2] for l in timeline.splitlines()[1:]] == ["stage_view", "start", "join", "end", "act"]
    assert f"{a} 2026-11-28T00:00:00+09:00 end cc=\"KR\" dev=\"mobile\" players=1 secs=20" in timeline
    assert b not in timeline and bot not in timeline and "never-print-this" not in timeline
    assert "2026-11-27" not in cli("--since", "2026-11-28")
