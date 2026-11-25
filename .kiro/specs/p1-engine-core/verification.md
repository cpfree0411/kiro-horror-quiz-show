# P1 — verification: requirement → test

All tests are in `tests/`. `scripts/test.sh` runs them (179 fast tests, about 85 s; schema validation of every message and of a snapshot after every step dominates the time).

| Req | Evidence |
| --- | --- |
| A1 no I/O, injected clock/RNG/tokens | `Engine(...)` takes `clock`, `rng`, `token_factory`; `test_lobby::test_credential_tokens_do_not_come_from_the_seeded_rng`; no network imports in `server/` |
| A2 determinism | `test_secrecy_and_determinism::test_same_seed_same_inputs_gives_the_identical_stream` |
| A3 `next_due`/`poll`, no stage needed | `test_stage_gates::test_pump_keeps_running_when_every_stage_is_gone`, `::test_game_continues_with_no_stage_connected_at_all` |
| A4 pure rules | `test_rules_judge`, `test_rules_scoring_betrayal`, `test_rules_captions`, `test_content_model` |
| B1 sseq contiguous, per game, kept | every sim asserts `[sseq] == 1..n`: `test_stage_gates::test_gate_ids_follow_sseq…`, `test_secrecy…::test_secrecy_scan…`, `test_scenario_final_reconnect::…reconnect…` |
| B2 snapshot sseq ≥ 1, lobby opens with `phase.changed lobby` | `test_engine_smoke`, `test_scenario_final_reconnect::…reconnect…` (snapshot does not consume a number) |
| B3 every message and a snapshot per step validated | `support/harness.py::Sim._validate` runs in every simulation test; `test_scanner_and_mc_contract::test_scanner_catches_hidden_buzzer_text…` shows the schema rejecting a leak |
| B4 one gate, id `g-<sseq>` | `test_stage_gates::test_gate_ids_follow_sseq_and_one_gate_at_a_time`; `Engine.open_gate` raises if one is open |
| B5 ack rules, safety timeout | `test_stage_gates::test_wrong_id_wrong_sseq_and_viewer_acks…`, `::test_matching_ack_closes_and_duplicates_and_stale_acks_are_harmless`, `::test_safety_timeout_is_timeout_ms_plus_25s…` |
| B6 reaction after ack | `test_stage_gates::test_reaction_starts_only_after_ack…`, `test_scanner_and_mc_contract::test_reactions_carry_public_results_only_after_the_ack` |
| B7 primary / viewer | `test_stage_gates::test_hello_always_gets_a_snapshot_and_second_primary_becomes_viewer` |
| B8 ping, need_snapshot, media_ready, viewers ignored | `test_stage_gates::test_ping_pong_need_snapshot_media_ready_and_unknown_socket`, `test_windows_and_config::test_viewers_cannot_report_media_or_beats` |
| C1–C4 names, seats, fans, credentials | `test_lobby` (16 tests) |
| C5 mode, start | `test_lobby::test_start_rules_and_join_after_start`, `test_phone_and_final::test_solo_finale` |
| C6 disconnect | `test_buzzer_voice::test_disconnected_player_cannot_buzz_or_answer`, `test_phone_and_final::test_early_finish_ignores_disconnected_players…` |
| D1–D3 windows, deadlines, gate table | `test_windows_and_config`, `test_scenario_solo_and_duo::test_betrayal_timeout…` (16 s), `test_buzzer_voice::test_answer_window_deadline…`, `::test_open_window_is_15s…`, `test_music_edges` (800 ms, 10 s, watchdog) |
| E1 OX flow, missing picks | `test_scenario_solo_and_duo::test_missing_pick_breaks_unanimity_and_is_omitted`, `::test_nobody_answers_skips_the_empty_reveal` |
| E2 points | `test_phone_and_final::test_points_per_kind`, `::test_settlement_exactly_once…` |
| E3 streak | `test_scenario_solo_and_duo::test_streak_resets…`, `::test_solo_never_unanimous…` |
| E4 target, never "last" | `test_secrecy_and_determinism::test_no_shaming_words_anywhere_the_engine_writes`, `test_scenario_solo_and_duo::test_duo_act1_betrayal_matches_scenario`, `::test_betrayal_timeout_keeps_the_pick_and_never_says_last`, `test_rules_scoring_betrayal` |
| E5 betrayal sequence | scenario test above; `test_phone_and_final::test_betrayal_actions…`, `::test_betrayal_by_voice` |
| F1 hidden text | `test_scenario_trio_buzzer_music::test_early_buzz_cuts_the_mc_and_text_comes_only_after_the_reading_played` |
| F2 first buzz | `test_buzzer_voice::test_first_buzz_wins_and_duplicates_locked_and_unarmed_are_rejected`, trio test (mcInterrupted, stale token) |
| F3 holder, early wrong/correct | `test_buzzer_voice::test_early_correct_answer_ends_the_reading…`, `::test_everyone_locked_out_still_reveals_text…`, `::test_wrong_buzz_in_open_window…` |
| F4 no `answer_heard` | `test_buzzer_voice::test_exact_for_regular_korean_alias_ok_and_answer_heard_never_sent`, `test_scanner…::test_player_speech_is_never_in_the_stream` |
| F5 suspense, points | `test_scenario_trio_buzzer_music::test_buzzer_round_has_suspense_and_judging_before_every_verdict` |
| F6 one music question | `test_content_model::test_select_builds_eight_questions_in_show_order` |
| F7 music collision rules | `test_scenario_trio_buzzer_music::test_music_collision_rules_and_interrupt`, `test_music_edges` |
| F8 hints | `test_music_edges::test_nobody_buzzes_goes_through_both_hints…`, `::test_eligibility_is_per_level…`, trio hint test |
| F9 credits | `test_scenario_trio_buzzer_music::test_credit_only_in_answer_revealed` |
| G1 bets | `test_phone_and_final` (invalid bets table, limits, missing bet, zero at zero, no text during betting in `test_scenario_final_reconnect`) |
| G2 reveal order | `test_scenario_final_reconnect::test_bets_reveal_lowest_first…` |
| G3 final settlement | `test_phone_and_final::test_wrong_and_missing_answers_lose_the_bet…` |
| G4 ranks, ties | `test_phone_and_final::test_tie_for_the_win_and_shared_ranks` |
| G5 ending | `test_scenario_final_reconnect::test_final_allin_matches_scenario` (tail), `::…stream_stops_after_ended` |
| H1–H2 voice answers | `test_buzzer_voice` (recognition failure, unvoiced, empty, two failures → text box, choose typing, stale listen) |
| H3 `answer_matches` | `test_rules_judge` |
| I1–I3 secrecy | `test_secrecy_and_determinism` (5 random full games, bet canaries, MC commands), `test_scanner_and_mc_contract` (5 mutation tests prove the scan fails when a leak is planted) |
| I4 captions | `test_rules_captions`, `test_scanner_and_mc_contract` caption tests |
| I5 logs | `test_secrecy_and_determinism::test_logs_carry_phase_and_player_count_only` |
| J1 five scenario themes | `test_scenario_solo_and_duo` (themes 1, 2), `test_scenario_trio_buzzer_music` (3), `test_scenario_final_reconnect` (4, 5) — compared message by message against `interface/scenarios/*.json` |
| J4 frozen boundary, no network | `test_frozen_boundary` (manifest + validator) still passes; nothing in `tests/` opens a socket or reads an env file |

## Not verified in P1
- Nothing ran against the real stage page or a browser; the engine's stream was only checked against the schema and the scenario files. The stage's handling of the leading `phase.changed lobby` and of `finale.curtain` was checked by reading `stage.js`, not by running it.
- The caption filter is heuristic. It is tested on examples, not on real Live output.
- MC cue wording, real playback timing, `mc.status` timing against real audio: P3.
- `SystemClock` and the real timer pump: P2.
- Fixture content only; the English bank and real music clips are P4.
