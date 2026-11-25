# P3 — verification: requirement → evidence

Fast tests: 319 passed (`scripts/test.sh`). Slow tests: all 10 passed in a final parallel run after the last code change. slow ones with `scripts/test.sh -m slow …`. Real-API evidence is in `/srv/workdata/build-cache/khqs-evidence/p3/` (outside the repo). **Tests never call the live API.**

| Req | Evidence |
| --- | --- |
| A1–A4 bank file | `tests/test_bank_io.py` (dev bank loads, validates, round-trips; every field present; 25 broken-file cases each give a clear error; Hangul alias warns; missing/malformed file; the validator command's output and exit codes), `tests/server/test_bank_server.py` (KHQS_BANK, invalid bank stops startup with errors, music served from the file's asset ids), `docs/QUESTION_BANK_FORMAT.md`, `scripts/check_bank.sh` |
| B1 key handling | `test_live_mc::test_gemini_transport_reads_the_key_only_at_connect…` (key read at connect from the given file, not stored on the object, not in logs or the session log), `::test_missing_key_and_provider_errors_are_sanitized` (provider text and the key never reach an error message); `grep -rn GEMINI_API_KEY` shows only the variable name in `transport.py` |
| B2 no reconnect loop | `::test_connect_failure_leaves_the_mc_offline_and_nothing_retries`, `::test_provider_close_goes_offline_show_continues…` (one transport after the close; explicit reconnect makes the second), `::test_goaway_resumes_with_the_handle_at_most_four_times_then_stops`, `::test_without_a_resume_handle_goaway_stops` |
| B3 caps | `::test_caps_stall_inactivity_and_session_length` (40 min, 240 s, 35 s response stall), `::test_playback_that_never_reports_stops_the_mc_safely…` |
| B4 operator-only, counted | settings refuse a live MC on a non-loopback stage host; `/api/mc/*` and `/ws/mc` exist only on the stage app (`test_ports_and_pages` walks them against both ports); `sessions_opened` asserted; the session log holds time and purpose only |
| B5 no API in tests | every test above uses `FakeTransport`; the real transport is exercised only with the SDK stubbed |
| C1–C2 turn per line, playback cursor | `test_connect_one_session_status_follows_real_playback_and_gate_waits_for_it` (the engine waits for the browser's played report); browser: `test_live_mc_browser` (every played line was reported by the real page; started ⊇ played) |
| C3 status from real playback | `tests/test_engine_live_modes.py`; `test_live_mc` (no `speaking` from generation alone); browser test; real run: 80 `mc.status` changes, 36 lines started and 36 played |
| C4 interrupt | `::test_interrupt_flushes_discards_old_audio_and_survives_interrupted_then_late_turn_complete`, `::test_a_buzz_that_cuts_a_reading_in_flight_still_opens_the_mic…` (a bug the first real run found; the test fails without the fix) |
| C5 music silence | engine contract from P1 (`test_music_edges`); with the live MC the adapter drops mic audio while the engine mic gate is closed (`handle(McMic)`) |
| C6 captions | `test_nothing_sent_to_the_model_leaks…` (a model that blurts each buzzer answer: none reaches the stage); `test_rules_captions` |
| D1–D3 listening | `::test_mic_opens_only_for_a_listen_and_silence_never_reaches_live`, `::test_no_tool_call_or_no_voiced_audio_is_a_recognition_failure…`, `::test_a_tool_call_without_voiced_evidence_does_not_count`, `tests/test_mc_prompts_voice.py` (VoiceMeter) |
| D4–D5 tools | `::test_spoken_answer_becomes_a_tool_call_with_silent_receipt_and_the_engine_judges`, `::test_stale_or_wrong_tool_calls_get_a_silent_receipt…` |
| E1–E3 secrecy | `::test_nothing_sent_to_the_model_leaks_a_secret_before_its_reveal…` (a full game: every prompt, tool result and caption scanned with the P1 scanner), `test_mc_prompts_voice` (each cue uses only its own facts; players cannot forge a cue; system prompt rules); real runs: the scan of every prompt sent was clean |
| F1–F3 browser host, START flow, chip | `test_live_mc_browser` (START connects mic, socket and session before the show; chip shows MC ONLINE); real runs |
| F4 collapsible pad | `test_live_mc_browser` (edge tab only while nothing needs the pad player; panel opens when it does; hidden at the curtain so NEW SHOW is never covered); `test_live_games` still pass with the new pad |
| G1 English-only docs | `grep -in korean docs/GAME_RULES.md docs/HANDOFF.md .kiro/steering` shows only the scope-change notes |
| G2 handoff | README sections "Run it", settings table, "Live MC", "Question bank", "Handoff", "Known limits" |
| H1 unit tests with a fake Live session | `tests/server/test_live_mc.py`, `tests/server/live_rig.py` |
| H2 browser test, fake transport | `tests/e2e/test_live_mc_browser.py` |
| H3 real smoke runs | below |
| H4 human voice | **not done** (owner) |

## Real Live sessions opened by this agent (free tier)
| # | When | Purpose | Result |
| --- | --- | --- | --- |
| 1 | 05:46 | `speech-fixture`: have the model say "Mirror" for the fake microphone | 0.84 s of speech |
| 2 | 05:47 | `play`: full solo game, headless Chromium, fake mic | game completed; found the drain bug (below) |
| 3 | 05:56 | `play`: same, with voice evidence logging | completed; `heard: "Mirror"`, clear, voiced; scan clean; the first Q4 buzz had been cut off by the drain bug |
| 4 | 06:07 | `play`: after the fix | completed; Q4 `heard: "mirror"`, clear, voiced, accepted and judged correct locally; Q5 (music, same clip) judged wrong as expected; 35 lines played; scan clean |

Real runs reported: one session per game (`sessions_opened == 1`), zero gate timeouts, page errors 0, podium and NEW SHOW correct, secrecy scan of all prompts clean.

## Not verified
- A human voice, room echo and real speakers (the owner's play test). The fake microphone is a synthesized clip of the model's own voice.
- Korean or other languages (out of scope by decision).
- Behaviour at the real free-tier limits (429 and session caps): the code reports `MC OFFLINE — TRY AGAIN` and goes offline, tested with injected errors only.
- `send_client_content(turn_complete=False)` (the listen context line) is accepted by the real model; its effect on behaviour was not measured.
