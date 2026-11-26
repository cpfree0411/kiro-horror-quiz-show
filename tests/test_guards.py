"""Pure guards: classification, client address, rate limits, socket budgets, operator secret."""
import logging

import pytest

from khqs.server.guards import (LOCAL, PUBLIC, OperatorAuth, RateLimiter, SocketBudget, classify, client_ip, hostname)
from khqs.server.settings import Settings, SettingsError

PUB = Settings(public=True, public_host="demo.example.com", operator_secret="s" * 20, phone_host="127.0.0.1", allow_loopback_phone=True)
NORMAL = Settings()


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.mark.parametrize("h,expect", [("127.0.0.1:18830", "127.0.0.1"), ("LocalHost", "localhost"), ("[::1]:18830", "::1"), ("Demo.Example.com:443", "demo.example.com"), ("", "")])
def test_hostname(h, expect):
    assert hostname(h) == expect


def test_classify_local_requires_loopback_host_loopback_peer_and_no_forwarding_headers():
    assert classify({"host": "127.0.0.1:18830"}, "127.0.0.1", PUB) == LOCAL
    assert classify({"host": "localhost:9000"}, "::1", NORMAL) == LOCAL
    for hdr in ("x-forwarded-for", "cf-connecting-ip", "forwarded", "x-real-ip", "cf-ray", "x-forwarded-host"):
        assert classify({"host": "127.0.0.1:18830", hdr: "1.2.3.4"}, "127.0.0.1", PUB) is None, hdr  # looks proxied: never local
    assert classify({"host": "127.0.0.1:18830"}, "203.0.113.9", PUB) is None  # loopback host name from a remote peer


def test_classify_public_only_in_public_mode_for_exactly_the_configured_host():
    h = {"host": "demo.example.com", "cf-connecting-ip": "203.0.113.5"}
    assert classify(h, "127.0.0.1", PUB) == PUBLIC
    assert classify({"host": "Demo.Example.com:443"}, "127.0.0.1", PUB) == PUBLIC
    assert classify(h, "127.0.0.1", NORMAL) is None  # without public mode there is no public class
    for bad in ("evil.example", "demo.example.com.evil.example", "xdemo.example.com", "example.com", ""):
        assert classify({"host": bad}, "127.0.0.1", PUB) is None, bad


def test_client_ip_trusts_forwarding_only_from_a_loopback_peer():
    assert client_ip({"cf-connecting-ip": "203.0.113.5"}, "127.0.0.1") == "203.0.113.5"
    assert client_ip({"x-forwarded-for": "198.51.100.7, 10.0.0.1"}, "::1") == "198.51.100.7"
    assert client_ip({"cf-connecting-ip": "203.0.113.5"}, "198.51.100.9") == "198.51.100.9"  # spoofable from elsewhere: ignored
    assert client_ip({"cf-connecting-ip": "not an ip"}, "127.0.0.1") == "127.0.0.1"
    assert client_ip({}, "") == "unknown"


def test_rate_limiter_window_keys_and_bounded_state():
    c = Clock()
    r = RateLimiter(2, 300, c, max_keys=4)
    assert r.allow("a") and r.allow("a") and not r.allow("a")
    assert r.allow("b")
    c.t += 299
    assert not r.allow("a")
    c.t += 2
    assert r.allow("a")  # the window slid
    for k in "wxyz":
        r.allow(k)
    assert r.size() <= 4
    c.t += 1000
    assert r.allow("fresh") and r.size() <= 4  # expired keys are dropped before refusing
    flood = RateLimiter(1, 1000, c, max_keys=3)
    assert [flood.allow(f"k{i}") for i in range(5)] == [True, True, True, False, False]  # a flood of keys cannot grow the table


def test_socket_budget_per_address_and_total_and_release():
    b = SocketBudget(per_ip=2, total=3)
    assert b.acquire("a") and b.acquire("a") and not b.acquire("a")
    assert b.acquire("b") and not b.acquire("c")  # total of 3
    b.release("a"); b.release("a"); b.release("a")  # an extra release is harmless
    assert b.acquire("c") and b.count == 2
    for ip in ("a", "b", "c", "c"):
        b.release(ip)
    assert b.count == 0 and b.size() == 0


def test_operator_auth_constant_time_lockout_and_no_secret_in_logs(caplog):
    caplog.set_level(logging.DEBUG)
    c = Clock()
    a = OperatorAuth("correct-horse-battery-staple", c)
    assert a.check("ip", "correct-horse-battery-staple") == "ok"
    for i in range(4):
        assert a.check("ip", f"guess-{i}") == "bad"
    assert a.check("ip", "guess-5") == "bad"  # the fifth failure triggers the lock
    assert a.check("ip", "correct-horse-battery-staple") == "locked"  # even the right secret waits out the lockout
    assert a.check("other", "correct-horse-battery-staple") == "ok"  # per client
    c.t += 61
    assert a.check("ip", "correct-horse-battery-staple") == "ok"
    assert a.check("ip", None) == "bad" and a.check("ip", 12345) == "bad"
    assert OperatorAuth(None).check("ip", "x") == "disabled"
    text = caplog.text
    assert "correct-horse" not in text and "guess-" not in text and "count=" in text
    assert "operator_secret" not in repr(PUB) and "ssssss" not in repr(PUB)


def test_public_settings_guards():
    ok = dict(public=True, public_host="demo.example.com", operator_secret="x" * 16)
    assert Settings(**ok).validate().join_url == "https://demo.example.com/ticket.html"
    for bad in (dict(public_host=""), dict(public_host="https://demo.example.com"), dict(public_host="demo.example.com:443"), dict(public_host="a b"),
                dict(public_host="demo.example.com/x"), dict(operator_secret=None), dict(operator_secret="short"), dict(mc="live", operator_secret=None)):
        with pytest.raises(SettingsError):
            Settings(**{**ok, **bad}).validate()
    with pytest.raises(SettingsError):
        Settings(public=True, public_host="d.example.com", operator_secret="x" * 16, stage_host="192.168.50.216").validate()


def test_env_for_public_mode_reads_the_secret_file_without_keeping_it_in_the_repr(tmp_path):
    f = tmp_path / "op.secret"
    f.write_text("a-long-operator-secret-value\n")
    s = Settings.from_env({"KHQS_PUBLIC": "1", "KHQS_PUBLIC_HOST": "Demo.Example.com", "KHQS_OPERATOR_SECRET_FILE": str(f)})
    assert s.public and s.public_host == "demo.example.com" and s.operator_secret == "a-long-operator-secret-value"
    assert "a-long-operator" not in repr(s) and "a-long-operator" not in str(s)
    with pytest.raises(SettingsError):
        Settings.from_env({"KHQS_PUBLIC": "1", "KHQS_PUBLIC_HOST": "demo.example.com"})
