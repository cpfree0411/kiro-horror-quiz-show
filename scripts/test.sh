#!/usr/bin/env bash
# Run the test suite with the project venv. Extra arguments go to pytest:
#   scripts/test.sh                 fast tests
#   scripts/test.sh -m slow         long browser checks
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${KHQS_VENV:-/srv/workdata/projects/.venvs/kiro-horror-quiz-show}"
export PYTHONDONTWRITEBYTECODE=1
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/srv/workdata/browser-cache/ms-playwright}"
exec "$VENV/bin/python" -B -m pytest -o cache_dir="${KHQS_PYTEST_CACHE:-/srv/workdata/build-cache/khqs-pytest}" "$@"
