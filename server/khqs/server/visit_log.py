"""Opt-in public demo events, with bounded, off-loop disk I/O."""
from __future__ import annotations

import fcntl
import hmac
import json
import logging
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Full, Queue
from threading import Event, Thread

log = logging.getLogger("khqs.server")
MAX_BYTES = 50_000_000
COUNTRY = re.compile(r"[A-Z]{2}|T1")
BOT = re.compile(r"bot\b|crawl|spider|slurp|curl|python|wget|headless|lighthouse|preview|facebookexternalhit")


def device(user_agent: str) -> str:
    ua = user_agent.lower()
    if BOT.search(ua):
        return "bot"
    if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        return "tablet"
    if any(word in ua for word in ("mobile", "iphone", "ipod", "android")):
        return "mobile"
    if any(word in ua for word in ("windows", "macintosh", "linux", "x11", "cros")):
        return "desktop"
    return "other"


@dataclass(frozen=True)
class Visitor:
    vid: str
    cc: str | None
    dev: str


class VisitLog:
    def __init__(self, path: Path, key: bytes) -> None:
        self._key = key
        self._pending = Queue(maxsize=512)
        self._stopped = Event()
        self._writer = Thread(target=self._write, args=(path,), name="khqs-visits", daemon=True)
        self._writer.start()

    def visitor(self, address: str, country: str, user_agent: str) -> Visitor:
        vid = hmac.digest(self._key, address.encode(), "sha256").hex()[:12]
        return Visitor(vid, country if COUNTRY.fullmatch(country) else None, device(user_agent))

    def record(self, now_ms: int, visitor: Visitor, event: str, **fields: str | int) -> None:
        if not self._stopped.is_set():
            try:
                self._pending.put_nowait((now_ms, visitor, event, fields))
            except Full:
                pass  # a slow disk must never hold up play or grow the queue

    def close(self) -> None:
        self._stopped.set()
        try:
            self._pending.put_nowait(None)
        except Full:
            pass  # the writer will exit after draining the queue
        self._writer.join(timeout=1)

    def _write(self, path: Path) -> None:
        warning = None
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8", buffering=1) as out:
                info = os.fstat(out.fileno())
                if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_uid != os.geteuid() or info.st_nlink != 1):
                    raise OSError("unsafe visit log file")
                fcntl.flock(out.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                size = os.fstat(out.fileno()).st_size
                while not self._stopped.is_set() or not self._pending.empty():
                    item = self._pending.get()
                    if item is None:
                        break
                    now_ms, visitor, event, fields = item
                    stamp = datetime.fromtimestamp(now_ms // 1000, UTC).isoformat()
                    line = json.dumps({"t": stamp, "ev": event, "vid": visitor.vid, "cc": visitor.cc,
                                       "dev": visitor.dev, **fields}, separators=(",", ":")) + "\n"
                    size += len(line)  # json.dumps escapes non-ASCII, so characters equal UTF-8 bytes
                    if size > MAX_BYTES:
                        warning = "visit log stopped at the size limit"
                        break
                    out.write(line)
        except OSError:
            warning = "visit log stopped after a storage error"
        finally:
            self._stopped.set()
            if warning is not None:
                log.warning(warning)
