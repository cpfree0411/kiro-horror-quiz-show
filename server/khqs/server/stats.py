"""Process and host measurements for the soak runs: memory, descriptors, tasks, timers and the host's tables."""
from __future__ import annotations

import asyncio
import gc
import os
import sys
import threading


def _status_kb(field: str) -> int:
    with open("/proc/self/status", encoding="ascii") as f:
        for line in f:
            if line.startswith(field + ":"):
                return int(line.split()[1])
    return 0


def descriptors() -> tuple[int, int]:
    """(open descriptors, of which sockets)"""
    n = socks = 0
    for fd in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        n += 1
        socks += target.startswith("socket:")
    return n, socks


def process_stats(host=None, loop: asyncio.AbstractEventLoop | None = None) -> dict:
    """Call on the event loop's thread (use `collect` from another thread)."""
    gc.collect()
    fds, socks = descriptors()
    loop = loop or asyncio.get_running_loop()
    out = {
        "rss_kb": _status_kb("VmRSS"), "fds": fds, "sockets": socks, "threads": threading.active_count(),
        "tasks": len([t for t in asyncio.all_tasks(loop) if not t.done()]),
        "timers": len([h for h in getattr(loop, "_scheduled", []) if not h.cancelled()]),
        "blocks": sys.getallocatedblocks(),
    }
    if host is not None:
        out.update(stage_socks=len(host.stage), phone_socks=sum(len(v) for v in host.phones.values()), mc_pending=len(host.mock_mc._pending),
                   stream_len=len(host.engine.stream), game_index=host.game_index, phase=host.engine.phase)
        for provider in host.stats_providers:
            out.update(provider())
    return out


def collect(server) -> dict:
    """From another thread: measure a `RunningServer` on its own loop."""
    loop = server.holder["loop"]

    async def go():
        return process_stats(server.host, loop)
    return asyncio.run_coroutine_threadsafe(go(), loop).result(30)
