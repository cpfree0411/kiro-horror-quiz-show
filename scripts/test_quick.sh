#!/usr/bin/env bash
# The quick test subset (a few seconds): pure rules, content and banks, MC prompts and voice meter, guards, hooks.
# The full fast suite (about two minutes) is `scripts/test.sh`.
set -euo pipefail
cd "$(dirname "$0")/.."
exec scripts/test.sh -q -x tests/test_rules_judge.py tests/test_rules_scoring_betrayal.py tests/test_rules_captions.py tests/test_content_model.py \
  tests/test_bank_io.py tests/test_en_bank.py tests/test_mc_prompts_voice.py tests/test_guards.py tests/test_frozen_boundary.py \
  -p no:cacheprovider
