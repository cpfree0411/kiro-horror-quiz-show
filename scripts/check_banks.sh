#!/usr/bin/env bash
# Validate every question bank in banks/ with scripts/check_bank.sh (limits, answer-in-text scan, aliases, files). Quick.
set -euo pipefail
cd "$(dirname "$0")/.."
status=0
for f in banks/*.json; do
  if ! out=$(scripts/check_bank.sh "$f" 2>&1); then
    echo "BANK INVALID: $f" >&2
    echo "$out" | grep -E "ERROR|NOT usable" | head -12 >&2
    status=1
  else
    echo "$out" | tail -1
  fi
done
exit $status
