"""Run both listeners in one event loop. Used by `python -m khqs.server` and by tests."""
from __future__ import annotations

import asyncio
import logging
import threading

import uvicorn

from ..content.bank_io import BankError, load_bank
from ..content.dev_bank import build_dev_bank
from .app import build_apps
from .host import GameHost
from .settings import Settings

log = logging.getLogger("khqs.server")


def _config(app, host: str, port: int) -> uvicorn.Config:
    # access_log off: nothing sensitive in URLs, and logs carry only phase and player count
    # guards.py needs the original socket peer to decide whether to trust forwarding headers.
    return uvicorn.Config(app, host=host, port=port, access_log=False, proxy_headers=False, log_level="warning",
                          ws_max_size=1 << 20, lifespan="off")


async def serve(settings: Settings, ready: threading.Event | None = None, holder: dict | None = None, host_factory=GameHost) -> None:
    settings.validate()
    try:
        bank = load_bank(settings.bank_path, settings.media_dir) if settings.bank_path else build_dev_bank(settings.media_dir)
    except BankError as e:
        raise SystemExit(f"question bank {settings.bank_path} is not usable:\n{e}") from None
    host = host_factory(settings, bank)
    stage_app, phone_app = build_apps(host, settings)
    servers = [uvicorn.Server(_config(stage_app, settings.stage_host, settings.stage_port)),
               uvicorn.Server(_config(phone_app, settings.phone_host, settings.phone_port))]
    for s in servers:
        s.install_signal_handlers = lambda: None
    host.start_pump()
    if holder is not None:
        holder.update(host=host, servers=servers, loop=asyncio.get_running_loop())
    tasks = [asyncio.create_task(s.serve()) for s in servers]
    while not all(s.started for s in servers):
        if any(t.done() for t in tasks):
            break
        await asyncio.sleep(0.02)
    log.info("listening stage=%s:%d phone=%s:%d", settings.stage_host, settings.stage_port, settings.phone_host, settings.phone_port)
    if ready:
        ready.set()
    try:
        await asyncio.gather(*tasks)
    finally:
        await host.stop()


class RunningServer:
    """The server in a background thread (tests, headless runs)."""

    def __init__(self, settings: Settings, host_factory=GameHost) -> None:
        self.settings = settings
        self.host_factory = host_factory
        self.holder: dict = {}
        self.ready = threading.Event()
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        try:
            asyncio.run(serve(self.settings, self.ready, self.holder, self.host_factory))
        except BaseException as e:  # noqa: BLE001
            self.error = e
            self.ready.set()

    def start(self) -> "RunningServer":
        self.thread.start()
        if not self.ready.wait(20) or self.error:
            raise RuntimeError(f"server did not start: {self.error!r}")
        return self

    @property
    def host(self) -> GameHost:
        return self.holder["host"]

    def stop(self) -> None:
        loop = self.holder.get("loop")
        if loop:
            for s in self.holder["servers"]:
                s.should_exit = True
        self.thread.join(10)
