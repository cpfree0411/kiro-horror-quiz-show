#!/usr/bin/env bash
# Everything a hook may run at the end of an agent turn: manifest, banks, quick tests. Exit 1 with the reason on stderr.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
scripts/check_manifest.sh >/dev/null || { scripts/check_manifest.sh >&2; fail=1; }
scripts/check_banks.sh >/dev/null 2>/tmp/khqs_banks.err || { cat /tmp/khqs_banks.err >&2; fail=1; }
if ! out=$(scripts/test_quick.sh 2>&1); then echo "QUICK TESTS FAILED:" >&2; echo "$out" | tail -15 >&2; fail=1; fi
exit $fail
