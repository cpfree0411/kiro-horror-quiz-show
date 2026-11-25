"""Injectable time source. The engine never calls time.* directly."""
from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> int:
        """Server epoch milliseconds."""


class SystemClock:
    def now_ms(self) -> int:
        return time.time_ns() // 1_000_000


class FakeClock:
    """Manual clock for tests and replays."""

    def __init__(self, start_ms: int = 1_761_300_000_000) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int) -> int:
        if ms < 0:
            raise ValueError("clock cannot go backwards")
        self._now += ms
        return self._now
