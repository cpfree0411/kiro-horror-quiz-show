# P7 — verification: requirement → evidence

Fast suite (`scripts/test.sh`): 542 passed, 12 deselected (slow). Quick subset (`scripts/test_quick.sh`): 243 passed in about 11 s. Slow tests: all passed in a parallel run on the final code (logs in `/srv/workdata/build-cache/khqs-evidence/p7/`, outside the repo). **Tests never call the live API; P7 opened no real Gemini session.**

| Req | Evidence |
| --- | --- |
| A1 clips and ladder unchanged | `tests/test_music_hints.py::test_the_ladder_still_lengthens_the_clip_with_one_short_line_and_no_clue` (plays 0, 1, 2 with the same clips), existing `test_scenario_trio_buzzer_music`, `test_music_edges` (updated for the new cue) |
| A2 no clue on the ladder | same test (only `longer_listen {level, max_level}`, no `hint_*` cue); `test_scenario_trio_buzzer_music::test_the_automatic_step_resets_eligibility_and_speaks_no_clue`; `test_mc_prompts_voice::test_only_the_granted_hint_turn_carries_a_clue…` |
| A3 spoken hints only on request | the same tests; no `hint_grant` without a request in any ladder test |
| R1 request at every level, during and after the music | `test_music_hints.py::test_a_voice_request_at_each_level_asks_the_others_then_grants_clue_one…` (levels 0, 1, 2, each during the clip and after it; the clip case asserts `mediaInterrupted`) |
| R2 model reports, engine decides | `rules/hints.py`; `test_hint_rules.py` (phrase lists); `tests/server/test_live_mc.py::test_a_spoken_hint_request_is_reported_verbatim_and_the_engine_alone_decides` (the fake model calls `report_answer` with the words; the engine turns it into a request; the receipt is silent) |
| R3 an answer is never a hint request | `test_hint_rules.py::test_an_answer_that_also_says_hint_is_an_answer`, `::test_the_answer_rule_uses_the_judge…`; `test_music_hints.py::test_an_answer_that_also_says_hint_is_judged_as_an_answer` |
| R4 HINT button, same engine path | `test_the_hint_button_is_offered_only_to_the_holder…`, `::test_the_button_path_uses_the_same_engine_flow_as_voice_with_a_mock_mc_that_cannot_hear`, `::test_the_button_is_refused_outside_the_music_question_and_after_the_limits`; browser: `tests/e2e/test_music_hint_browser.py` (real phone and pad pages, mock MC) |
| R5 a request is not an answer | `test_a_voice_request…` (no `buzzer.judged`, no attempt, no lock before the answer), `::test_an_unclear_or_unvoiced_hint_phrase_is_a_recognition_failure_not_a_request`, `::test_a_typed_hint_word_is_an_answer_the_button_is_the_way_to_ask` |
| C1 ask line and 8 s window | `::test_the_consent_window_opens_a_listen_for_the_room_and_closes_it`, `::test_silence_for_the_whole_window_counts_as_yes_after_eight_seconds` (exactly 8000 ms) |
| C2 agree / refuse, any refusal refuses | `test_hint_rules.py::test_agree`, `::test_refuse_and_any_refusal_refuses`; `test_music_hints.py::test_a_refusal_wins_over_agreement_even_when_the_yes_came_first`, `::test_spoken_votes_agree…`, `::test_a_spoken_no_refuses_at_once…`; live: `test_consent_by_voice_two_reports_in_one_window_any_no_refuses…` |
| C3 silence and unclear count as yes | `::test_silence_for_the_whole_window…`, `::test_one_yes_and_one_silent_voter_is_granted_when_the_window_ends`, `::test_a_spoken_no_refuses_at_once_and_unclear_speech_changes_nothing` |
| C4 AGREE / NO on the phones | `::test_a_voice_request_at_each_level…` (screens `hint_wait`, `hint_vote`, `hint_voted`), `::test_votes_are_validated_and_final`; browser test (select NO or AGREE, LOCK IN) |
| C5 solo | `::test_solo_has_nobody_to_ask_the_mc_grants_with_a_joke_and_there_is_no_window`, `::test_a_disconnected_player_is_not_asked…` |
| G1 order clue 1, clue 2, composer | `::test_the_hints_come_in_order_clue_one_clue_two_the_composer` |
| G2 requester answers at once; +20 / lock-out; round goes on | `::test_a_voice_request_at_each_level…` (+20), `::test_a_wrong_answer_after_the_hint_locks_the_requester_out…`, `::test_everyone_wrong_after_hints_still_continues_the_automatic_ladder…` |
| G3 refused | `::test_consent_refused_by_a_phone_no_ends_the_window_at_once…`, `::test_a_refused_requester_who_answers_wrong_is_locked_out_as_usual` |
| G4, G5 limits | `::test_no_hints_left_after_three_then_the_player_must_answer…`, `::test_each_player_may_ask_once…`, `::test_asking_again_at_a_later_level_is_still_once_per_question`, `::test_a_refused_request_gives_nothing_so_the_next_player_gets_clue_one` |
| V1 nothing early | `::test_the_clues_and_the_composer_are_not_in_any_cue_facts_until_granted`; live: the fake model's every turn, context and system prompt scanned for clue, composer, title (`test_live_mc.py` P7 tests); `::test_an_agreed_hint_hands_the_model_exactly_one_clue_at_the_moment_it_is_granted` |
| V2, V3 stage, snapshots, views, captions | `assert_no_leaks` (extended: each clue and the composer are secret until the first `hint_grant` carrying them) over 16 full games that use hints (`::test_full_games_that_use_hints_leak_nothing`, `::test_hint_games_across_seeds_do_use_hints…` asserts hints were really used), `::test_the_scan_catches_a_clue_handed_out_before_the_grant`, `::test_captions_of_a_granted_composer_pass_the_filter_only_after_the_grant…`, `::test_the_stage_stream_only_shows_the_hint_phase_and_no_new_message_types`; browser test scans everything the browsers received |
| B1 composer in the bank format | `tests/test_bank_io.py` (six new broken-file cases, round trip, `hints` order), `tests/test_content_model.py`, `docs/QUESTION_BANK_FORMAT.md`, `scripts/check_banks.sh` |
| B2 bank values | `banks/en-bank.json` diff is three added lines (`git diff c9aaa01 -- banks/en-bank.json`); `tests/test_en_bank.py::test_every_english_track_has_its_composer…`; dev bank has the same values |
| S1 stage frozen | `sha256sum -c MANIFEST.sha256`; `git diff faa43b1 --stat -- stage interface` is empty; see the report for what the existing wire shows |

## Fix after the owner's live play test: the MC never spoke the hint
Cause: the model's turn that made the `report_answer` call ends with a `turn_complete` of its own just after the tool response. The engine said `hint_grant` within a few ms of the tool call, so that `turn_complete` ended the new cue with no audio (44 ms in the owner's log). It was not a P7-only bug: any cue sent right after a tool call was exposed (`offer_switch` after the betrayal reason, `react_betrayal` after the decision, `hint_*` after a vote); the answer path was safe only because its next cue comes seconds later, after a gate.
Fix (`server/khqs/mc/live.py`): the next cue waits for the end of the tool-call turn (at most `TOOL_TURN_S` = 1.5 s); a hint cue that ends with no audio is sent once more, and a second empty turn is logged; count-only log lines for each cue sent (`mc cue sent cue=… try=…`), each cue done (`mc cue done cue=… audio_ms=…`), each tool call (`mc tool call name=…`), and a turn_complete outside a cue.
Tests (`tests/server/test_live_mc.py`, fake transport now models the open tool turn: `tests/server/live_rig.py`): `test_a_cue_sent_right_after_a_tool_call_is_not_ended_by_the_tool_turns_own_turn_complete` fails on 9b10881 (the grant never produced audio), `…_no_completion_after_the_tool_response_still_speaks_the_hint`, `…_empty_turn_for_a_hint_cue_is_retried_once…`, `…_two_empty_turns_are_logged…`, `…_other_hint_cues_are_also_checked…`, `…_log_shows_each_cue_sent…` (no player words, clue, composer or title in any log line).
Real API: `scripts/live_smoke.py hint <dir>` was written for one deliberate check. Its first run opened the one allowed session and stopped on a script mistake (the simulated player counted as disconnected after the join grace); the script was fixed and passes a dry run against the fake transport. A second real session was not opened without the owner's permission, so **the fix is not yet confirmed against the real model**.

## Worst case length of the music question
`scripts/music_timing.py`: fake clock, mock MC line durations (60 ms per character, 0.9 to 6 s), every gate acked after 1.5 s, every clip played to its end, a buzz in the last 100 ms of every open window, every answer window run to its end, three players.

| Case | Seconds | Minutes |
| --- | --- | --- |
| Today (P6 code): every level fails, three timed-out answers per level, a long clue line per level | 371.0 | 6.2 |
| P7, nobody asks (ladder line is shorter) | 364.6 | 6.1 |
| P7, all three players ask at the last moment, nobody votes, all granted (8 s windows, then a fresh 20 s answer window each) | 470.5 | 7.8 |
| P7, all three ask, the first voter says NO at the last moment, all refused | 460.8 | 7.7 |

Each ask adds up to about 35 s in the worst case (the ask line, 8 s of consent, the grant or refusal line, and a fresh answer window).

## Not verified
- A human voice for the hint request and for the spoken yes or no (only the fake Live session was used). The model's reliability at calling `report_vote` once per speaker, and at passing "hint" phrases verbatim, is untested against the real API.
- Several people talking at once during the consent window.
- A real room echo while the MC asks the others.
- Hooks firing in a Kiro session (second attempt this phase, same session; nothing fired).
