"""Server settings from the environment, with guards for the port split."""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RESERVED_PORTS = frozenset({8814, 18815, 18817, 18818})  # other services on this host: never bind
LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1")


class SettingsError(ValueError):
    pass


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Settings:
    stage_host: str = "127.0.0.1"
    stage_port: int = 18830
    phone_host: str = "192.168.50.216"
    phone_port: int = 18831
    public_phone_url: str | None = None
    stage_dir: Path = REPO / "stage"
    media_dir: Path = REPO / "media"
    seed: int | None = None
    mock_speed: float = 1.0  # 2.0 = the mock MC talks twice as fast (tests)
    buzzer_answer_ms: int = 20_000
    record: bool = False
    allow_loopback_phone: bool = False  # tests only
    join_grace_s: float = 10.0  # a joined player with no phone socket by then is shown as disconnected

    def validate(self) -> "Settings":
        if not _is_loopback(self.stage_host):
            raise SettingsError("the stage listener must stay on loopback (127.0.0.1)")
        try:
            ip = ipaddress.ip_address(self.phone_host)
        except ValueError:
            raise SettingsError(f"phone host must be an IP address, got {self.phone_host!r}") from None
        if ip.is_unspecified:
            raise SettingsError("the phone listener must bind to one LAN address, never 0.0.0.0 or ::")
        if ip.is_loopback and not self.allow_loopback_phone:
            raise SettingsError("the phone listener needs a LAN address (loopback is allowed only in tests)")
        for name, port in (("stage", self.stage_port), ("phone", self.phone_port)):
            if port in RESERVED_PORTS:
                raise SettingsError(f"{name} port {port} is reserved for another service")
        if self.stage_port and self.stage_port == self.phone_port:
            raise SettingsError("stage and phone ports must differ")
        return self

    @property
    def join_url(self) -> str:
        return self.public_phone_url or f"http://{self.phone_host}:{self.phone_port}/ticket.html"

    @classmethod
    def from_env(cls, env=os.environ) -> "Settings":
        g = env.get
        kw: dict = {}
        if g("KHQS_STAGE_PORT"):
            kw["stage_port"] = int(g("KHQS_STAGE_PORT"))
        if g("KHQS_PHONE_HOST"):
            kw["phone_host"] = g("KHQS_PHONE_HOST")
        if g("KHQS_PHONE_PORT"):
            kw["phone_port"] = int(g("KHQS_PHONE_PORT"))
        if g("KHQS_PUBLIC_PHONE_URL"):
            kw["public_phone_url"] = g("KHQS_PUBLIC_PHONE_URL")
        if g("KHQS_SEED"):
            kw["seed"] = int(g("KHQS_SEED"))
        if g("KHQS_MOCK_SPEED"):
            kw["mock_speed"] = float(g("KHQS_MOCK_SPEED"))
        if g("KHQS_BUZZER_ANSWER_MS"):
            kw["buzzer_answer_ms"] = int(g("KHQS_BUZZER_ANSWER_MS"))
        if g("KHQS_ALLOW_LOOPBACK_PHONE") == "1":
            kw["allow_loopback_phone"] = True
        return cls(**kw).validate()
