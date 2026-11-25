import sys
from pathlib import Path

import pytest

# Never write .pyc files next to frozen sources (interface/tools/ would count as an extra file).
sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO
