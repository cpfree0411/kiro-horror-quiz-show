import pytest

from khqs.server.runner import RunningServer
from settings_util import free_port, make_settings  # noqa: F401  (re-exported for the server tests)


@pytest.fixture
def server():
    srv = RunningServer(make_settings()).start()
    yield srv
    srv.stop()
