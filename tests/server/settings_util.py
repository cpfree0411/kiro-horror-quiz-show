import socket

from khqs.server.settings import Settings


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def make_settings(**kw) -> Settings:
    base = dict(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True,
                record=True, seed=7, mock_speed=4.0, disconnect_grace_s=0.05)
    base.update(kw)
    return Settings(**base).validate()
