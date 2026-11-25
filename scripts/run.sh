#!/usr/bin/env bash
# Run the show: stage on 127.0.0.1:18830, phones on the LAN address :18831 (see README). Ctrl-C stops it.
# Settings (all optional): KHQS_STAGE_PORT, KHQS_PHONE_HOST, KHQS_PHONE_PORT, KHQS_PUBLIC_PHONE_URL, KHQS_SEED, KHQS_BUZZER_ANSWER_MS
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${KHQS_VENV:-/srv/workdata/projects/.venvs/kiro-horror-quiz-show}"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="server${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV/bin/python" -B -m khqs.server
