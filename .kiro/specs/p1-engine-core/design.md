# P1 — Engine core: design

## 1. Shape

One synchronous, I/O-free `Engine` per game. Outside code feeds it **inputs** and drains **effects**. A single generator (`_game`) sequences the show; it yields `Wait` objects and the engine resumes it when a matching event arrives or the wait's deadline passes.

```
 inputs ──►  Engine (state, rules, generator)  ──► effects (outbox)
 stage msgs, phone actions, MC events, poll()     stage stream/direct, MC commands, phone-changed
```

Why a generator: the show is a long, linear script of waits (gate, MC playback, player input, deadline). A generator reads like the rules document. Public state lives in plain fields, not in the generator position, so snapshots and phone views never depend on it.

Only one wait is live at a time, so there is one timer: `next_due()` returns the active wait's deadline.

## 2. Modules (`server/khqs/`)

| Module | Content | Pure |
| --- | --- | --- |
| `clock.py` | `Clock` protocol, `SystemClock`, `FakeClock` | yes |
| `rules/judge.py` | `normalize`, `answer_matches` | yes |
| `rules/scoring.py` | `rank_scores`, `valid_bet`, `ox_deltas`, `final_deltas`, `bet_reveal_order`, `winners`, `lead_set` | yes |
| `rules/betrayal.py` | `update_streak`, `pick_target`, `flip` | yes |
| `rules/captions.py` | `CaptionFilter` (per-utterance state) | yes |
| `content/model.py` | `Question`, `MusicTrack`, `QuestionSet`, `ContentBank`, `GameContent`, validation | yes |
| `engine/config.py` | `EngineConfig` (all windows, gate timeouts, caps) | yes |
| `engine/effects.py` | effect dataclasses (stage, phone, MC) | yes |
| `engine/core.py` | `Engine`: state, stream, gates, timers, stage intake, snapshots, phone views, input handlers | no I/O |
| `engine/flow.py` | the generator: lobby→opening→acts→finale (split into act functions) | no I/O |
| `engine/views.py` | snapshot and phone-view builders (public / private projections) | yes |

`tests/support/` holds the harness (fake stage, fake MC, scenario comparison, secrecy scanner). The harness is test code; the mock MC for the live server is P2.

## 3. Effects (engine → outside)

| Effect | Fields | Consumer |
| --- | --- | --- |
| `StageBroadcast(msg)` | a stream message (has `sseq`) | all stage sockets |
| `StageDirect(conn, msg)` | snapshot, `pong`, `error` | one socket |
| `PhoneChanged(seats)` | seats whose private view changed | controller sockets |
| `McSay(token, cue, facts, spoken_by_engine=True)` | cue name + public facts | MC adapter |
| `McListen(listen_id, seat, purpose, attempt, deadline)` | purpose `answer`/`reason`/`decision` | MC adapter |
| `McStopListen(listen_id)` | | MC adapter |
| `McInterrupt(reason)` | flush and cancel current speech | MC adapter + browser |
| `McMic(open, reason)` | mic forwarding on/off | connector + MC |

MC → engine inputs: `mc_played(token)` (output cursor reached the end), `mc_failed(token)`, `mc_voice_answer(listen_id, heard, recognition, voiced)`, `mc_voice_reason(listen_id, heard)`, `mc_voice_decision(listen_id, switch)`, `mc_caption(utterance_id, text, final)`.

**Tokens.** Every MC line that gates progress carries a token. The engine keeps a set of live tokens. `McInterrupt` or a buzz removes them. `mc_played` for a token that is not live is ignored (stale). If `mc_enabled=False` the engine resolves every `McSay` at once and issues no `McListen`.

**Cues** (the MC adapter owns wording; the engine owns facts): `greeting`, `act_intro`, `read_ox`, `read_buzzer`, `intro_music`, `hint_line`, `suspense`, `ask_reason`, `offer_switch`, `react_betrayal`, `react_answer`, `react_judge`, `ask_again`, `phone_fallback`, `final_intro`, `read_final`, `react_winner`, `farewell`. Every fact dict is whitelisted per cue in one table (`CUE_FACTS`), and a test checks no cue carries an answer, alias, explanation or correct choice before reveal.

## 4. Gates and reactions

| Gate | timeoutMs | Reaction cue (starts after stage ack) |
| --- | ---: | --- |
| `show.opening` | 60000 | none (greeting is a separate waited line after the gate) |
| `act.started` | 8000 (act 3: 10000) | `act_intro` |
| `question.presented` ox | 5000 | `read_ox` |
| `question.presented` buzzer | 5000 | none (the reading is a separate, interruptible line) |
| `question.presented` av | 5000 | `intro_music` |
| `question.presented` final | 6000 | `read_final` |
| `ox.choices_revealed` | 6000 | none |
| `betrayal.offered` | 6000 | `ask_reason` |
| `betrayal.decided` | 6000 | `react_betrayal` |
| `answer.revealed` | ox 6000, buzzer 5000, final 7000 | `react_answer` |
| `score.settled` | ox 5000, buzzer 5000, final 7000 | none |
| `buzzer.judged` | 5000 | `react_judge` (no answer) |
| `av.hint` | 5000 | `hint_line` (private clue) |
| `final.category` | 6000 | none |
| `final.choices_revealed` | 7000 | none |
| `final.bet_revealed` | 6000 | none |
| `finale.winner` | 12000 | `react_winner` |
| `finale.results` | 15000 | `farewell` |

Gate safety = `timeoutMs + 25000` from opening. A gate with a reaction closes when ack **and** reaction done (played, failed, or stale). A reaction issued after the ack is bounded by the same safety deadline.

## 5. Waited lines (not gate reactions)

`greeting` (after the opening gate; fail-safe 15 s), `final_intro` (15 s), `suspense` (15 s), `offer_switch` (15 s), `read_buzzer` (reading fail-safe 45 s, interruptible), `ask_again` and `phone_fallback` (fire and forget).

## 6. Public state held by the engine

`phase`, `phase_started_at`, `deadline`, `act`, `question_no`, current `Question` (public view), `revealed_text`, `round` (kind-specific public round), `open_gate`, `mc_status`, `revealed_answer`, seats with scores and ranks. Secret state (picks, bets, aliases, answers, reasons, credentials, RNG) lives in separate private fields never read by the snapshot builder; the builder takes an explicit allow-list.

## 7. Time and determinism

`Engine(content, clock, rng, config, token_factory, game_index, mc_enabled)`. RNG draws happen only at: fan assignment, music track choice, betrayal tie. Credentials never use the seeded RNG (they must be unguessable); the token factory is injected (`secrets.token_urlsafe` by default, counter in tests).

## 8. Decisions

| Topic | Decision | Reason |
| --- | --- | --- |
| Rank style | Competition ranking (1,1,3) | Common for scoreboards; the stage clamps pod art to 1–3 either way. Open to change. |
| Lock-in | First OX pick, first final pick and first bet are final | Matches "duplicate bets rejected", prevents timing games. Phone UI should confirm taps. |
| Early finish | A waiting window ends early when every **connected** player has submitted (and at least one is connected) | Duo scenario reveals right after the last pick; a dropped phone must not stall the show for 20 s every question. |
| Holder timeout | Counts as a wrong answer and locks the holder out | Otherwise the question would stall. Voice failures never count (H2). |
| After a wrong buzz | Back to `buzzer.open` with a fresh window (15 s regular, 10 s music) | Each wrong answer removes one eligible player, so it terminates. |
| `mc.status` | `speaking` when a line is issued, `idle` when it is played, failed or stale, `listening` while a listen is open | The stage mouth follows `mc.status`; the adapter can refine timing in P3. `thinking` is not used. |
| Reconnect resend | Always a snapshot, never a replay | Allowed by interface §8; simplest and always correct. |
| First stream message | `phase.changed lobby` at game creation | A snapshot needs `sseq ≥ 1`. The stage's `phase.changed` handler is harmless in the lobby. |
| Unknown gate ack | Reply `error unknown_gate` to that socket, no state change | Same shape as the interface example; harmless to the connector. |
| Phase for `betrayal.listening` | stays `ox.betrayal`; the 8 s windows are on the phone view's `deadline` only | Matches the duo scenario (no extra `phase.changed`). |
| `tiedSeats` for a unique lowest | `[]` | The schema requires the field; a roulette needs no candidates. |
| Gate timeouts | The interface §4 table and the scenarios (e.g. `final.choices_revealed` 7000, `act.started` 10000 for act 3), not the rules §4 summary | The interface is the wire truth and more specific. |
| No MC (`mc_enabled=False`) | Says resolve at once, no listens, holder gets the text box; a buzzer reading therefore takes no time | For tests and headless runs. The P2 mock MC is `mc_enabled=True` with simulated durations. |
| Voice answer window | Recognition retries share one window (the deadline does not move) | The public `deadline` stays true. |
| Asserts | Guards that protect rules (one gate, settle once, no negative score, cue whitelist) raise exceptions, not `assert` | They must survive `python -O`. |
| `finale.curtain` | Emitted before the `finale.results` gate | The stage draws the finale rest pose from a snapshot only in `finale.curtain` or `ended` (stage.js line 792), so a reconnect during the results gate needs it. Matches the scenario. |
| Accent folding | Not applied in `answer_matches` | Rules say exact after NFKC/case/space/punctuation; authors add aliases (P4). |

## 9. Divergences from the scenario files (intended)

1. Buzzer rounds add `phase.changed buzzer.suspense` + `answer.suspense` before `answer.revealed` (rules §6; the scenario omits it).
2. `finale.results` (rev 1.1) sits between `phase.changed finale.curtain` and `phase.changed ended`; `game.ended` follows as in the scenario.
3. `mc.status` is ignored in comparisons; the engine drives it from playback state.
4. The engine opens the lobby with `phase.changed lobby` (sseq 1).
5. Scenario sample content (questions, fans) is reproduced by fixtures where the data matters.
6. A joining player takes the lowest free seat (solo: seat 0). The solo scenario shows seat 1; the stage's own demo entry also uses the lowest free seat.
7. `buzzer.judging` is sent before every `buzzer.judged` (the scenario omits it once, in its music tail), and the scenario's `lockedOut: [1]` after a hint is `[]` here because a hint resets eligibility (rules §6.1).
8. Float seconds (`12.0`) are sent where the scenario has `12`; the same JSON number.
9. `av` question ids are `q-av-<number>`; the scenario's `q-av-02` is a sample.

## 10. Open questions for the owner

1. Competition vs dense ranking (§8).
2. First-pick-final for OX and final choices (§8).
3. Buzzer default answer window when no MC is attached (20 s) vs live (60 s): chosen by the P2/P3 config, not hard-coded.
