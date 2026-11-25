"""Wait objects the game generator yields, and the gate record."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Wait:
    """Resume the generator when `ready()` is true or `until` (absolute server ms) passes.

    The generator re-reads engine state after resuming; it is not told which condition fired.
    """

    until: int | None = None
    ready: Callable[[], bool] | None = None


@dataclass
class Gate:
    id: str
    sseq: int
    type: str
    timeout_ms: int
    opened_at: int
    safety_at: int
    reaction: tuple[str, dict] | None = None  # (cue, public facts); starts after the stage ack
    acked: bool = False
    token: str | None = None
