#!/usr/bin/env bash
# Validate a question bank file (docs/QUESTION_BANK_FORMAT.md). Usage: scripts/check_bank.sh path/to/bank.json
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${KHQS_VENV:-/srv/workdata/projects/.venvs/kiro-horror-quiz-show}"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="server${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV/bin/python" -B -m khqs.content.check "$@"
