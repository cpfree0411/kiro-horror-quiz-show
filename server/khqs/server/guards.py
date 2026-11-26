"""Access guards for the stage listener: who is asking, how often, and with which secret. Pure, clock-injectable.

`classify` is the single place that decides whether a request is local (the owner, directly or through an SSH tunnel)
or public (through the demo tunnel). Forwarding headers are trusted only when the peer is loopback, i.e. the tunnel itself.
"""
from __future__ import annotations

import hmac
import ipaddress
import logging
import time
from collections import deque

from .settings import LOOPBACK_NAMES, Settings

log = logging.getLogger("khqs.server")
LOCAL, PUBLIC = "local", "public"
FORWARD_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip", "forwarded", "cf-connecting-ip", "cf-ray",
                   "cf-visitor", "cf-ipcountry", "true-client-ip", "x-original-forwarded-for")
SECRET_HEADER = "x-khqs-operator"


def hostname(host_header: str) -> str:
    h = (host_header or "").strip().lower()
    if h.startswith("["):
        return h[1: h.index("]")] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def is_loopback_peer(peer: str) -> bool:
    try:
        return ipaddress.ip_address(peer).is_loopback
    except ValueError:
        return peer == "localhost"


def classify(headers, peer: str, settings: Settings) -> str | None:
    """local | public | None (refuse). Without public mode only local exists."""
    host = hostname(headers.get("host", ""))
    forwarded = any(h in headers for h in FORWARD_HEADERS)
    if host in LOOPBACK_NAMES and is_loopback_peer(peer) and not forwarded:
        return LOCAL
    if settings.public and host and host == settings.public_host.lower():
        return PUBLIC
    return None


def client_ip(headers, peer: str) -> str:
    """The address to rate-limit: the tunnel's view of the visitor when the peer is the tunnel, else the peer."""
    if is_loopback_peer(peer):
        for name in ("cf-connecting-ip", "x-forwarded-for"):
            v = (headers.get(name) or "").split(",")[0].strip()
            try:
                return str(ipaddress.ip_address(v))
            except ValueError:
                continue
    return peer or "unknown"


class RateLimiter:
    """At most `limit` events per `window_s` per key. State is bounded: expired keys are dropped, and the table is capped."""

    def __init__(self, limit: int, window_s: float, clock=time.monotonic, max_keys: int = 2048) -> None:
        self.limit, self.window, self.clock, self.max_keys = limit, window_s, clock, max_keys
        self._hits: dict[str, deque] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        if len(self._hits) >= self.max_keys:
            self.prune(now)
            if len(self._hits) >= self.max_keys:
                return False  # a flood of distinct keys: refuse rather than grow
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    def prune(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= self.window]:
            del self._hits[k]

    def size(self) -> int:
        return len(self._hits)


class SocketBudget:
    """Concurrent sockets: per client address and in total."""

    def __init__(self, per_ip: int, total: int) -> None:
        self.per_ip, self.total = per_ip, total
        self._by_ip: dict[str, int] = {}
        self._n = 0

    def acquire(self, ip: str) -> bool:
        if self._n >= self.total or self._by_ip.get(ip, 0) >= self.per_ip:
            return False
        self._by_ip[ip] = self._by_ip.get(ip, 0) + 1
        self._n += 1
        return True

    def release(self, ip: str) -> None:
        if self._by_ip.get(ip, 0) > 0:
            self._by_ip[ip] -= 1
            self._n -= 1
            if self._by_ip[ip] == 0:
                del self._by_ip[ip]

    @property
    def count(self) -> int:
        return self._n

    def size(self) -> int:
        return len(self._by_ip)


class OperatorAuth:
    """The operator secret: constant-time compare, lockout after repeated failures, count-only logging."""

    FAILS, WINDOW_S, LOCK_S = 5, 60.0, 60.0

    def __init__(self, secret: str | None, clock=time.monotonic) -> None:
        self._secret = secret.encode() if secret else None
        self.clock = clock
        self._fails: dict[str, deque] = {}
        self._locked: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return self._secret is not None

    def check(self, key: str, supplied) -> str:
        """'ok' | 'bad' | 'locked' | 'disabled'"""
        if self._secret is None:
            return "disabled"
        now = self.clock()
        until = self._locked.get(key)
        if until is not None:
            if now < until:
                return "locked"
            del self._locked[key]
        if isinstance(supplied, str) and hmac.compare_digest(supplied.encode(), self._secret):
            self._fails.pop(key, None)
            return "ok"
        q = self._fails.setdefault(key, deque())
        while q and now - q[0] >= self.WINDOW_S:
            q.popleft()
        q.append(now)
        log.warning("operator secret rejected count=%d", len(q))  # never the value, never the attempt
        if len(q) >= self.FAILS:
            self._locked[key] = now + self.LOCK_S
            q.clear()
        if len(self._fails) > 1024:
            self._fails = {k: v for k, v in self._fails.items() if v and now - v[-1] < self.WINDOW_S}
        return "bad"
