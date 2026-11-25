#!/usr/bin/env bash
# Create the dev virtualenv outside the repo and install the dev dependencies.
# Caches go under /srv/workdata, set per command (no global environment overrides).
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${KHQS_VENV:-/srv/workdata/projects/.venvs/kiro-horror-quiz-show}"
UV_CACHE="${KHQS_UV_CACHE:-/srv/workdata/cache/uv}"
[ -x "$VENV/bin/python" ] || uv venv --cache-dir "$UV_CACHE" "$VENV"
uv pip install --cache-dir "$UV_CACHE" --python "$VENV/bin/python" -e '.[dev]'
echo "venv: $VENV"
