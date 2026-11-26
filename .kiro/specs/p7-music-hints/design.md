# P7 — design

## Where the logic lives
| Piece | File | What |
| --- | --- | --- |
| Phrase lists and classification | `server/khqs/rules/hints.py` | `is_hint_request(heard, answer, aliases, kind)` (an answer by the judge always wins), `classify_consent(heard)` → agree / refuse / unclear |
| State | `server/khqs/engine/rounds.py` | `BuzzRound`: `hint_asked`, `hints_given`, `hint_request`, `hint_notice`, `consent`, `composer_out`; `Consent`: requester, voters, votes by seat, spoken yes/no counts |
| Engine inputs | `server/khqs/engine/core.py` | `phone_action hint` and `hint_vote`; `mc_voice_answer` (a clear, voiced, non-answer hint phrase sets `hint_request`); `mc_voice_consent`; `can_ask_hint`; caption secrets |
| Flow | `server/khqs/engine/flow.py` | `answer_phase` loops: window → (request → `hint_turn` → fresh window) → judge. `hint_turn`: set phase `buzzer.hint`, voters = connected others, ask line, consent window, refused line or the grant line |
| Phone views | `server/khqs/engine/views.py` | `own.canHint` for the holder in the music question; screens `hint_wait`, `hint_vote`, `hint_voted` |
| MC words | `server/khqs/mc/prompts.py`, `mock.py`, `engine/effects.py` | cues `longer_listen`, `hint_ask`, `hint_grant`, `hint_refused`, `hint_none` (replace `hint_line`); `report_vote` tool; consent listen context |
| Live adapter | `server/khqs/mc/live.py`, `transport.py` | tool `report_vote`; a consent listen stays open for several reports (re-armed, at most 4) until the engine ends the window |
| Phone UI | `server/khqs/server/web/phone.js`, `phone.css` | HINT? button on both answer screens; AGREE / NO with LOCK IN |
| Bank | `content/model.py`, `bank_io.py`, `docs/QUESTION_BANK_FORMAT.md` | required `composer`; `MusicTrack.hints` = clue 1, clue 2, composer |

## Decisions
1. **The engine decides, the model reports.** `report_answer` carries a hint request exactly like an answer. Nothing in the tool schema or the reply lets the model say "this was a hint request". The same engine entry (`hint_request = True`) serves voice and the HINT button.
2. **A request is not an answer.** `answer_phase` waits for `answer or hint_request`; a request ends the listen, runs `hint_turn`, then opens a **new** normal answer window (`buzzer_answer_ms`, text box or listen as before). The judged/locked/winner rules are untouched, so right is +20 and wrong locks out as before.
3. **Stage: no new wire messages.** The interface is frozen. `hint_turn` sets `phase.changed buzzer.hint` (the stage prints "HINT!" on its board for that phase) and the MC's spoken line reaches the stage as `mc.caption`. Votes, requests and the hint text are never on the stream.
4. **Consent window.** Voters = connected players other than the requester. None → solo path (no window, joke grant). `Consent.complete` = any refusal, or explicit yes count ≥ number of voters. Phone votes are by seat; spoken votes are counted without a seat (the room mic cannot tell who spoke); either source can refuse. Window end with no refusal = agree; "silence" vs "agreed" only changes the MC's joke.
5. **Limits.** `can_ask_hint(seat)`: music question, seat not in `hint_asked`, `hints_given < 3`. A refused ask is spent but gives no hint. A request that cannot be granted: `hint_none` line once (`hint_notice`), then a fresh window in which a hint phrase is an ordinary answer, so there is no loop. With three players each asking once the third hint can be the last; the "none left" branch protects against banks with fewer hints and manual state.
6. **Typed text is an answer.** Only voice is classified from text. Typing "hint" is a wrong answer; the button is the way to ask.
7. **Votes use select then LOCK IN**, like every other phone choice; the first vote is final. The HINT button is a single tap (it is not an answer and it spends only the player's own ask).
8. **Secrecy.** `hint_grant` is the only cue that carries a clue or the composer, and only when granted. The caption filter drops the composer from its blocked phrases once `composer_out`; the title, aliases, explanation and credit stay blocked. The test scanner (`tests/support/secrecy.py`) treats each clue and the composer as secret until the first `hint_grant` that carries it.
9. **Automatic ladder.** Unchanged except the reaction cue on the `av.hint` gate: `longer_listen` carries only the level, no clue.

## Timing (see `scripts/music_timing.py`, fake clock, mock MC line lengths, stage ack 1.5 s)
The adversary lets every clip play, buzzes in the last 100 ms of every open window and lets every answer window run out. With hints it asks in the last 100 ms of each window and nobody votes.
