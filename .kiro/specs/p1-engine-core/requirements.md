# P1 — Engine core: requirements

Sources: `docs/GAME_RULES.md` (rules), `interface/KHQS_STAGE_INTERFACE.md` and `interface/stage-protocol.schema.json` (wire), `docs/HANDOFF.md` §11 (P1 acceptance), steering files.

## Goal
A deterministic game engine with no network and no model. It takes inputs (stage messages, player actions, MC events, time) and produces effects (stage stream messages, MC commands, phone updates). Everything outgoing is validated against the schema in tests.

## Out of scope (later phases)
WebSocket server, connector, phone/pad UI, mock MC process (P2); Gemini Live (P3); the real English question bank and music clips (P4). P1 uses small fixture content only.

## Requirements

### A. Determinism and structure
| # | Requirement |
| --- | --- |
| A1 | The engine shall do no I/O. Time comes from an injected clock, randomness from an injected `random.Random`, credentials from an injected token factory. |
| A2 | Given the same seed, clock steps and inputs, the engine shall emit the same effects (byte-identical stream). |
| A3 | The engine shall expose `next_due()` and `poll()` so an outer loop owns sleeping. The timer pump shall work with no stage connected. |
| A4 | Rules (judging, scoring, ranking, betrayal selection, bet validation, caption filtering) shall be pure functions, unit-tested without the engine. |

### B. Stream and gates
| # | Requirement |
| --- | --- |
| B1 | The engine shall keep one stage stream per game: `sseq` starts at 1, rises by exactly 1, never gaps, is never consumed by snapshots, and every sent message is kept. |
| B2 | A snapshot shall carry the current `sseq` (at least 1), and a new game shall start the stream with `phase.changed lobby` so a lobby snapshot is valid. |
| B3 | Every outgoing message shall pass `check_engine_message` (zero problems), including snapshots taken after every engine step. |
| B4 | At most one gate shall be open. A gate id shall be `g-<sseq>`. The next gate shall not be sent while one is open. |
| B5 | A gate shall close when the primary stage sends `stage.beat_done` with the matching id **and** sseq, and the MC reaction (if any) has finished playing; or at `timeoutMs` + 25 s since opening. Viewer acks, wrong id, wrong sseq, duplicates and late acks shall change nothing. |
| B6 | The MC reaction to a gate shall start only after the stage ack (screen first, MC second). |
| B7 | The first `primary` hello wins. A later `primary` hello while one is connected shall be demoted to `viewer` and told so with an `error` (`primary_taken`). A hello shall always be answered with a snapshot. A primary disconnect shall free the slot. |
| B8 | `stage.need_snapshot` shall be answered with a snapshot; `stage.ping` with `pong`; `stage.media_ready` shall be recorded. Messages from viewers other than hello, ping and need_snapshot shall be ignored. |

### C. Lobby and players
| # | Requirement |
| --- | --- |
| C1 | `join(name)` shall work only in the lobby. Names are trimmed, 1–12 characters, unique (case-folded, NFKC), any script, no control characters. Errors are short English uppercase strings (`THAT NAME IS TAKEN`, `HOUSE FULL`, `TYPE A NAME`, `NAME TOO LONG`, `NO NAMES LIKE THAT`). |
| C2 | Seats are fixed 0–2; a join takes the lowest free seat; `seats` is always length 3 with vacant seats `player: null`. |
| C3 | Each player gets a different fan from `vampire`, `sack`, `bolt`, `tophat_skull`, chosen with the seeded RNG. |
| C4 | Each player gets an opaque private credential; it shall appear in no stage message, snapshot, log or other player's view. |
| C5 | Mode is `solo` for 1 player, `competitive` for 2–3, fixed at start. `start()` needs at least one player and lobby phase. |
| C6 | A disconnected player keeps the seat (`seat.connection`), cannot submit until reconnected, and does not hold up early-finish waits. |

### D. Time
| # | Requirement |
| --- | --- |
| D1 | Windows shall be: OX 20 s; betrayal reason and decision 8 s each; prompt/offer playback fail-safe 15 s; buzzer answer configurable (default 20 s, 60 s for live); buzzer open 15 s; music open 10 s; interrupt wait 800 ms; music watchdog clip length + 1 s; bet 20 s; final answer 20 s. All in one config object. |
| D2 | Every public `deadline` shall equal the real server-side deadline. |
| D3 | Gate `timeoutMs` shall follow the table in rules §4. |

### E. Act 1 (OX)
| # | Requirement |
| --- | --- |
| E1 | Flow as in rules §5 and the duo scenario. Picks are lockable once; a missing pick is wrong and breaks unanimity and is omitted from `ox.choices_revealed`; if all missed, the reveal is skipped. |
| E2 | Correct = +10, wrong or missing = 0; settlement happens exactly once per question. |
| E3 | Two consecutive fully unanimous rounds in competitive mode trigger the betrayal chance and reset the streak. Solo never emits `ox.unanimous` and never offers betrayal. A non-unanimous or incomplete round resets the streak. |
| E4 | The target is the current lowest score. A tie picks one with the seeded RNG (`tied_random`, `tiedSeats` sorted). The word "last" and its kin shall appear in no MC cue and no stage text produced by the engine. |
| E5 | Betrayal: offer gate → MC asks why → reason (phone button or voice, 8 s) → MC offers the switch → keep/switch (phone or voice, 8 s) → decision gate. Timeout keeps the pick. A switch flips the target's pick to the opposite and that pick is what is scored. Model output never grades the reason. |

### F. Act 2 (buzzer and music)
| # | Requirement |
| --- | --- |
| F1 | Regular buzzer questions shall present with `textHidden: true`, `text: null`, arm the buzzer during the reading, and reveal the text only after the matching reading token finished playing. |
| F2 | The first buzz by arrival wins. A buzz shall cut the MC (`McInterrupt`), mark the reading token stale, and set `mcInterrupted` only if the MC was reading. Duplicate buzzes, buzzes by locked-out or disconnected players, and buzzes while no buzzer is open are rejected without effect. |
| F3 | Only the holder can answer. A wrong answer or timeout locks the holder out and judges once. A wrong early answer resumes the reading with a fresh token; a correct early answer ends the reading and the unfinished text is never revealed. If nobody can still buzz, the text is still revealed after the reading resumes, then the round goes to suspense. |
| F4 | `buzzer.answer_heard` shall never be emitted. |
| F5 | Every buzzer round shall pass an acknowledged suspense step (`buzzer.suspense`, `answer.suspense`, MC suspense line played) before `answer.revealed`. Correct = +20, otherwise 0; no penalty. |
| F6 | Exactly one question in act 2 is the music question; the track is picked with the seeded RNG from the bank. |
| F7 | Music: the MC introduction finishes playing before `av.play`; from `av.play` to the matching `media_ended` the MC gets no commands and the mic is closed (`McMic(open=False)`). A buzz sets `mediaInterrupted: true`, waits for `media_ended(interrupted)` for at most 800 ms, then opens the answer. A natural end is accepted only if asset, level and position match; stale or duplicate ends never advance. A missing end is covered by the watchdog. |
| F8 | After a natural end, a 10 s buzz window opens. If everyone eligible is wrong or the window times out, the next hint level resets eligibility, goes through an `av.hint` gate with an MC clue line, and replays a longer clip. At the maximum level exhaustion goes to suspense and reveal. |
| F9 | Credits go out only in `answer.revealed.credit`. |

### G. Act 3 (final) and finale
| # | Requirement |
| --- | --- |
| G1 | Flow as in rules §7. Bets are integers in `[0, score]`; booleans, negatives, fractions, oversized, non-integers and duplicate bets are rejected; a missing bet is 0; bet 0 at score 0 is `allIn: true`. During betting no question text or choices appear anywhere. |
| G2 | One `final.bet_revealed` gate per player, ascending by pre-settlement score, ties by seat. Only revealed bets appear in snapshots. |
| G3 | Correct = +bet, wrong or missing = −bet. No negative balance results. Settlement happens exactly once. |
| G4 | Ranks: ties share a rank (competition ranking: 1, 1, 3). Winners are all rank-1 seats; `finale.winner.tie` is true when more than one. |
| G5 | After `finale.winner`: `finale.results` gate, then `phase.changed ended` and `game.ended`. The stream stops there. |

### H. Voice answers (engine side)
| # | Requirement |
| --- | --- |
| H1 | A voice answer arrives as `heard` (verbatim), `recognition` (`clear`/`unclear`) and a `voiced` flag, bound to the current listen id. Stale, duplicate or wrong-seat deliveries are ignored. |
| H2 | `unclear`, unvoiced, or empty `heard` is a recognition failure, not a wrong answer: the MC asks again. After two failures the holder's phone gets a text box and voice listening stops. A phone text answer, or a voice answer with evidence, is judged. The holder may also choose typing at once. |
| H3 | `answer_matches` shall implement rules §9.3: NFKC, case-fold, strip whitespace and punctuation, exact match against answer or alias; for music also substring (key length ≥ 3) and fuzzy window (ratio ≥ 0.8, key length ≥ 4). |

### I. Secrecy
| # | Requirement |
| --- | --- |
| I1 | No stage message or snapshot shall contain an answer, alias, explanation, OX pick, final pick, bet amount, buzzer text or music credit before its reveal event. |
| I2 | Snapshots are a strict public projection. A phone view shows only that player's own pick and bet. |
| I3 | MC commands issued before a reveal shall carry no answer, alias, explanation or correct choice. Reaction cues carry results only after the stage ack. |
| I4 | `mc.caption` shall pass a secret filter: never before reveal with an answer, alias, correct choice text or explanation (including partial leading words), no captions while a buzzer question is being read, one-letter answers blocked in assertion form, nothing more once an utterance trips the filter. |
| I5 | Logs shall carry phase and player count only: no names, answers or credentials. |

### J. Tests (acceptance)
| # | Requirement |
| --- | --- |
| J1 | Behaviour tests for the five scenario themes (solo opening, duo betrayal, trio buzzer + music + hint, trio all-in final, reconnect mid-reveal). Each compares the engine's stream against the scenario file (type order, key data) and lists every intended divergence. |
| J2 | Tests for gate id + sseq matching, duplicate and stale acks, settlement exactly once, snapshot projection without secrets. |
| J3 | A secrecy scan runs over every emitted stream, every snapshot taken after every step, other players' phone views, MC commands, captions and logs, using canary answers/bets. |
| J4 | The frozen boundary tests still pass; no test calls a network or the Gemini API. |
