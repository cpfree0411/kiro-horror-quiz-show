"""Optional recorder (tests): collects what the secrecy scanner needs, in the same shape as the test harness."""
from __future__ import annotations

import json


class Recorder:
    def __init__(self, host) -> None:
        self.host = host
        self.snapshots: list[dict] = []
        self.views: list[tuple[int, dict]] = []
        self.mc_fx: list[tuple[int, object, int]] = []
        self.directs: list[tuple[str, dict]] = []
        self.frames: list[dict] = []  # messages the browsers actually received (filled by browser tests)
        self._snap_key = None
        self._views = None

    @property
    def eng(self):
        return self.host.engine

    @property
    def stream(self):
        return self.host.engine.stream

    def on_mc(self, e) -> None:
        self.mc_fx.append((self.eng._sseq, e, self.host.clock.now_ms()))

    def on_direct(self, conn: str, msg: dict) -> None:
        self.directs.append((conn, msg))

    def observe(self) -> None:
        snap = self.eng.snapshot()
        key = (snap["sseq"], json.dumps(snap["data"], sort_keys=True))
        if key != self._snap_key:
            self._snap_key = key
            self.snapshots.append(snap)
        views = {s: self.eng.phone_view(s) for s in self.eng.players}
        if views != self._views:
            self._views = views
            self.views.append((self.eng._sseq, views))
