#!/usr/bin/env bash
# The frozen boundary: sha256sum -c MANIFEST.sha256, plus a check for files under stage/ or interface/ that are not in the manifest.
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${KHQS_VENV:-/srv/workdata/projects/.venvs/kiro-horror-quiz-show}"
if ! out=$(sha256sum -c MANIFEST.sha256 2>&1 | grep -v ': OK$'); then :; fi
if [ -n "${out:-}" ]; then
  echo "FROZEN BOUNDARY BROKEN: stage/ or interface/ no longer matches MANIFEST.sha256:" >&2
  echo "$out" | head -10 >&2
  exit 1
fi
extra=$(LC_ALL=C comm -13 <(awk '{print $2}' MANIFEST.sha256 | LC_ALL=C sort) <(find stage interface -type f | LC_ALL=C sort) || true)
if [ -n "$extra" ]; then
  echo "FROZEN BOUNDARY BROKEN: files that are not in MANIFEST.sha256:" >&2
  echo "$extra" | head -10 >&2
  exit 1
fi
echo "manifest OK ($(wc -l < MANIFEST.sha256) files)"
