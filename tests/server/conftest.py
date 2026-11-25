import socket
import sys
from pathlib import Path

import pytest

from khqs.server.runner import RunningServer
from khqs.server.settings import Settings


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def make_settings(**kw) -> Settings:
    base = dict(stage_port=free_port(), phone_host="127.0.0.1", phone_port=free_port(), allow_loopback_phone=True,
                record=True, seed=7, mock_speed=4.0)
    base.update(kw)
    return Settings(**base).validate()


@pytest.fixture
def server():
    srv = RunningServer(make_settings()).start()
    yield srv
    srv.stop()
