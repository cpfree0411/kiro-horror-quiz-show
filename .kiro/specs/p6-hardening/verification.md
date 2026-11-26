# P6 — verification: requirement → evidence

Fast suite (`scripts/test.sh`): 392 passed, 11 deselected as slow. Quick subset (`scripts/test_quick.sh`): 145 passed in about 10 s. Slow tests: 11 passed in a parallel run on the final code, including the new `tests/e2e/test_public_browser.py`. Soak output and logs are in `/srv/workdata/build-cache/khqs-evidence/p6/` (outside the repo). **Tests never call the live API; P6 opened no real Gemini session.**

## 1. Public demo mode

| Req | Evidence |
| --- | --- |
| P1 settings refuse bad public config | `tests/test_guards.py::test_public_settings_guards` (no host, host with scheme/port/path/space, non-loopback stage listener, live MC without a secret), `::test_hostname` |
| P2 local / public / refuse | `test_guards.py::test_classify_*`, `tests/server/test_public_mode.py::test_local_public_and_everything_else`, `::test_without_public_mode_the_public_host_is_refused`, `::test_origin_must_match_the_public_host` |
| P3 public gets the mock MC only | `::test_public_clients_get_the_mock_mc_no_operator_buttons_and_never_the_secret`, `::test_public_clients_cannot_reach_operator_actions_even_with_the_secret`; browser: `test_public_browser.py::test_public_visitor_and_local_operator_in_real_browsers` |
| P4 live MC only local with the secret; secret never leaks | `::test_live_mc_only_from_local_with_secret_and_the_show_turns_private`, `::test_local_operator_actions_need_the_secret_header_and_origin`, `test_guards.py::test_operator_auth_constant_time_lockout_and_no_secret_in_logs`, `::test_env_for_public_mode_reads_the_secret_file_without_keeping_it_in_the_repr`; the page-config and log scans are in the tests above |
| P5 lockout, count-only log | `test_public_mode.py::test_wrong_secrets_lock_the_client_out_and_the_log_never_has_a_secret` |
| P6 operator actions refused or secret-gated | `::test_public_clients_cannot_reach_operator_actions_even_with_the_secret` (force reset, `/api/mc/*`, `/ws/mc`, `/api/diag`, `take=1`), `::test_take_over_needs_the_operator_frame_before_the_hello` |
| P7 private show | `::test_live_mc_only_from_local_with_secret_and_the_show_turns_private` (503 `PRIVATE SHOW IN PROGRESS`, mock restored after the live MC stops), `::test_live_mc_refused_while_a_game_has_players_or_runs` |
| P8 one game, primary stage only | `::test_only_the_primary_stage_page_can_start_or_reset` |
| P9 caps | `::test_idle_game_resets_and_player_input_keeps_it_alive`, `::test_game_age_cap_resets_even_with_input` |
| P10 limits | `test_public_mode.py::test_join_limit_per_client_address`, `::test_start_and_reset_rate_limit`, `::test_socket_budgets_per_address_and_in_total`, `test_guards.py::test_rate_limiter_window_keys_and_bounded_state`, `::test_socket_budget_per_address_and_total_and_release`, `::test_client_ip_trusts_forwarding_only_from_a_loopback_peer` |
| P11 headers, join URL | `::test_security_headers_on_public_responses_only`; join URL asserted in `test_guards.py::test_public_settings_guards` and the browser test |
| P12 every guard has a test; tunnel documented, nothing deployed | rows above; `docs/PUBLIC_DEMO.md`; `::test_lan_phone_port_keeps_working_in_public_mode` shows the LAN phone app is unchanged. No tunnel, DNS or Cloudflare action was taken |

## 2. Soak and robustness

`scripts/soak.py` starts the server as its own process and reads `/proc/<pid>` plus `/api/diag` (`KHQS_DIAG=1`). In-process measurement was tried first and was polluted by the client threads.

### S1 — 30 back-to-back games through NEW SHOW (fixed code, 380 s)

| | start | game 2 | game 30 | final (stage closed) |
| --- | --- | --- | --- | --- |
| RSS (KB) | 41,152 | 41,448 | 41,452 | 41,452 |
| descriptors | 10 | 10 | 10 | 9 |
| sockets | 5 | 5 | 5 | 4 |
| threads | 1 | 1 | 1 | 1 |
| asyncio tasks | 7 | 7 | 7 | 5 |
| pending timers | 3 | 3 | 3 | 2 |
| stream length | 1 | 1 | 1 | 1 |

The stage client saw 30 game-ended events; `game_index` was 30. Python allocated blocks rose by 2,725 over the 30 games while RSS stayed flat (+4 KB), which is allocator churn, not a retained object (`tests/server/test_leaks.py::test_a_finished_game_can_be_garbage_collected_after_new_show` shows a finished game collected). Log: `games30_fixed.log`, data `soak_games.jsonl`.

### S2 — reconnect storms (fixed code)

Three rounds; each round has 600 phone connections (polite close, abrupt close, silent, bad credential, junk frames), 300 stage reconnects (same client id, take-over, viewers, abrupt closes) and 500 HTTP requests. After each round: descriptors 9, sockets 4, tasks 5, timers 2, host tables 0. RSS +0.5 MB from round 1 to round 3. Stream length +4 over the run. Data: `soak_storm.jsonl`.

### S3 — 60-minute idle server

Two server processes, one normal and one with `KHQS_PUBLIC=1`, sampled every 60 s (61 samples each).

| | normal t=0 | normal t=3600 s | public t=0 | public t=3600 s |
| --- | --- | --- | --- | --- |
| RSS (KB) | 40,800 | 40,908 (+108) | 40,828 | 40,936 (+108) |
| descriptors | 10 | 10 | 10 | 10 |
| sockets | 4 | 4 | 4 | 4 |
| threads | 2 | 2 | 2 | 2 |
| asyncio tasks | 5 | 5 | 6 | 6 |
| pending timers | 2 | 2 | 3 | 3 |
| limiter and stream tables | 0 and 1 | 0 and 1 | 0 and 1 | 0 and 1 |

No growth beyond 108 KB of RSS in an hour. Public mode has one more task and timer, the caps watchdog. These two runs started before the last leak fixes, but they never see a join, so the fixed code paths were not exercised. Files: `idle.log`, `idle_public.log`, `soak_idle.jsonl`, `soak_idle_public.jsonl`.

### S4 — leaks found and fixed

| Leak | Found by | Before | After | Regression test |
| --- | --- | --- | --- | --- |
| Join-grace timers never cancelled; each game kept two timers and an engine alive | 30-game soak (`games30.log`) | timers 4 to 63, RSS +5 MB | timers 3 to 3, RSS +4 KB | `test_leaks.py::test_a_finished_game_can_be_garbage_collected_after_new_show` |
| `Conn.close()` left the writer task running when the send queue was full | the soak work | one task per such socket | none | `::test_closing_a_socket_with_a_full_send_queue_does_not_leave_its_writer_task_behind` |
| A phone reload flapped the seat offline and online and sent each flap to the stage | first storm run | stream +1000 messages per round | +2 per round (2 s debounce, `disconnect_grace_s`) | `::test_a_phone_that_reloads_within_the_grace_time_is_never_announced_as_disconnected` |
| Baseline for all counters | | | | `::test_reconnect_storm_returns_descriptors_tasks_timers_and_tables_to_baseline` |

Three of these four tests were run against the code with the fixes removed and failed there. The fourth is a baseline check of all counters after a storm.

## 3. Hooks

| Req | Evidence |
| --- | --- |
| H1 hooks and scripts | `.kiro/hooks/frozen-boundary.json`, `bank-check.json`, `quick-tests.json`, `stop-gate.json`; `scripts/check_manifest.sh`, `check_banks.sh`, `test_quick.sh`, `check_all_quick.sh`. `scripts/check_all_quick.sh` run by hand takes seconds |
| H2 full suite not a hook | not in `.kiro/hooks/`; documented in `docs/KIRO_USAGE.md` and `README.md` |
| H3 hook tests | `tests/test_kiro_hooks.py` (18 tests): format, matchers hit and miss the right paths, commands are executable repo scripts, the manifest script fails on a changed or extra file in a temp copy, the bank script reports a broken bank in a temp copy, the stop gate runs all three checks quickly |

## 4. Docs

`docs/KIRO_USAGE.md` (what Kiro did, phase by phase, and what was made outside Kiro), `docs/PUBLIC_DEMO.md` (guards, settings, intended tunnel setup), README sections updated, `.kiro/steering/tech.md` extended.

## Boundary checks

`sha256sum -c MANIFEST.sha256` passes; `stage/`, `interface/`, `banks/en-bank.json` and `tests/test_en_bank.py` are unchanged from `c9aaa01`; the Gemini key value appears in no repo file or git history.

## Not verified

- A real Cloudflare tunnel. Public mode was tested with local requests that carry a public Host and forwarding headers. Real header behavior and latency over the internet are untested.
- The hooks firing inside a Kiro session. They were created with `createHook` and load at the next session start. The format, matchers and scripts are tested; the firing is not observed.
- A human voice with room echo on the live MC (owner's play-test).
- A soak with the live MC. All soaks used the mock MC.
- A 60-minute idle run on the final code. The two runs predate the last leak fixes (see S3).
