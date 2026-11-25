# Kiro Horror Quiz Show — Game Rules and Engine Behaviour

Status: handoff spec, 2026-11-25. Audience: the engine/MC implementer (Kiro).
Sources: the earlier prototype's engine spec (`KHQS_ENGINE_V1.md`), its play notes, its voice experiments, and the user's decisions. Everything below was proven in that prototype unless marked **NEW** (decided after it, not yet implemented anywhere).

The wire contract is `interface/KHQS_STAGE_INTERFACE.md` + `interface/stage-protocol.schema.json`. This document says **what the engine decides**; the interface says **what the stage is told**.

---

## 1. The show in one paragraph

A kitschy, cute Halloween TV quiz show hosted by a ghost MC (Gemini Live, voice). One to three players sit at fixed seats 0–2. Each player uses their own phone as a controller (QR ticket); a player without a phone can join on the main screen ("screen pad"). The show has an opening, three acts with eight questions, and a finale. The main screen (the frozen stage) shows everything; the MC speaks and listens.

## 2. Players, seats, modes

| Rule | Value |
| --- | --- |
| Players | 1–3 humans. No bots. No minimum of two |
| Seats | Fixed 0–2. `seats` on the wire is always length 3; empty seats are boarded up |
| Join order | First joiner takes the middle seat (1), then 0, then 2, so a solo player is centred |
| Mode | 1 player = `solo` (practice). 2–3 = `competitive` |
| Names | Unique, 1–12 characters. Any script (the stage draws them as typed) |
| Fan puppet | Assigned at join, fixed for the game, all different, from `vampire`, `sack`, `bolt`, `tophat_skull` (the only four with art). Seeded RNG |
| Credentials | Opaque and private per player. Never on the stage channel |
| Disconnect | Seat stays `occupied`; `seat.connection {connected:false}`. A disconnected player cannot submit until reconnected |

## 3. Layout and scoring

| Act | Questions | Kind | Correct | Wrong / missing |
| --- | --- | --- | --- | --- |
| 1 | 3 | OX (true/false) | +10 | 0 |
| 2 | 4 | Buzzer; **exactly one** is a music (audio AV) question | +20 | 0 (no penalty) |
| 3 | 1 | Four-choice final with a secret bet | +bet | −bet |

- Score settlement happens **exactly once** per question.
- No negative balances. Zero is a valid score.
- Final bet: integer in `[0, current score]`. Booleans, negatives, fractions, oversized and duplicate bets are rejected. Missing bet = 0. Betting 0 while at 0 counts as `allIn: true`.
- Ties share a rank; all tied top seats win (`finale.winner.tie: true`).
- Two question sets alternate between games; the music slot picks one of three recordings at random per game (seeded). **NEW:** the question bank must be rewritten in English (the prototype's bank is Korean) — see §10.

## 4. Time

The server clock owns phase start, elapsed time and deadlines (server epoch ms on the wire). Use one event loop / one worker; no threads or model calls own rules. The timer pump must keep running when every stage is gone.

| Window | Length |
| --- | --- |
| OX private answering | 20 s |
| Betrayal reason / decision input | 8 s each (prompt/offer playback fail-safe 15 s) |
| Buzzer answer (holder speaks) | 12 s in the original spec; **60 s with the live voice MC, 20 s with the mock MC** in the playable prototype (retries + phone fallback need the room). The public `deadline` must equal the real window |
| Buzzer open window after the reading | 15 s |
| Music: window after natural end | 10 s |
| Music: wait for `media_ended(interrupted)` after a buzz | 800 ms, then proceed |
| Music: watchdog for a missing natural end | clip length + 1 s |
| Final betting | 20 s |
| Final answering | 20 s |
| Gate timeouts (wire `timeoutMs`) | The table in `interface/KHQS_STAGE_INTERFACE.md` §4 is the wire truth (e.g. opening 60 s, act 8 s (act 3: 10 s), winner 12 s, results 15 s, final choices 7 s). The engine config mirrors it |
| Engine safety per gate | `timeoutMs` + 25 s (gate closes on stage `beat_done` **and** the MC reaction finishing playback) |

Client-provided `beats` are recorded but never override server limits.

## 5. Act 1 — OX and the betrayal chance

Flow: presentation gate → MC reads (wait for real playback end) → 20 s private answering → simultaneous choice reveal gate → `ox.unanimous` if applicable → optional betrayal → suspense (wait for real playback end of the MC's suspense line) → answer gate → score gate.

- A missing pick is wrong and breaks unanimity. Missing picks are omitted from `ox.choices_revealed` (the schema cannot encode null). If everyone missed, skip the empty reveal and go to suspense.
- **Betrayal trigger:** two consecutive fully unanimous rounds, competitive mode only. Solo keeps the streak at 0, never emits `ox.unanimous`, never offers betrayal.
- A non-unanimous or incomplete round resets the streak; triggering resets it too.
- **Target:** the current lowest score. If tied, seeded RNG over the sorted tied seats → `selection: "tied_random"`, `tiedSeats`.
- **Never say or show "last place", "last", "LAST", "worst" or similar.** Not in MC instructions, not on screen.
- Betrayal sequence: offer gate → MC asks the target why (playback) → target's reason (voice or phone button, 8 s) → MC offers the switch (playback) → target's boolean keep/switch (phone or voice, 8 s) → decision gate. **Timeout keeps the original pick.** No model grading or inference from free-form speech is authoritative; the MC only reacts to the reason.

## 6. Act 2 — buzzer

- After the presentation gate, regular questions arm the buzzer **during** the reading while the text stays hidden (`textHidden: true`, `text: null`).
- **First buzz wins by server arrival.** No client-timestamp arbitration.
- On a buzz: cut the MC at once (flush browser playback + interrupt Live), spotlight the holder. Early buzzing invalidates the current reading output.
- Only the holder can answer. A wrong answer locks that player out for this question. Duplicate buzzes or answers cannot judge twice.
- A wrong early answer resumes the reading with a fresh output token. Only a matching played-through acknowledgement reveals the full text (`question.text_revealed`). Eligible players can buzz during the resumed reading.
- A correct early answer ends the reading and the unfinished text is **never** revealed.
- `buzzer.answer_heard` is deliberately not emitted (forwarding a correct utterance would leak the answer before the official reveal).
- Buzzer rounds also go through an acknowledged suspense step before `answer.revealed`.

### 6.1 The music question (audio AV)

- The MC introduction ("Let's have a listen") must finish playing before `av.play`.
- **During music the MC is idle and the mic is closed** (no MC output, no mic forwarding to Live). The speakers would otherwise feed the music into the mic; software echo cancellation is off.
- A buzz emits `buzzer.pressed {mediaInterrupted: true}`. The stage stops the music within 100 ms and sends `stage.media_ended(interrupted)`. The answer mic opens only after the matching `media_ended` or the 800 ms fallback.
- A natural end opens a 10 s buzz window. Check asset, hint level, reason and absolute position; stale or duplicate ends cannot advance again.
- **Hints:** when everyone is wrong or the open window times out, the next hint level resets eligibility, goes through an `av.hint` gate and a short acknowledged MC line, then replays a **longer** clip (levels 0–2; e.g. 6/8 s → 14–20 s → full 30 s). At the max level, exhaustion goes to suspense and reveal.
- Each hint level has a private MC clue (instrument, mood, form — never the title). The MC says "Hint N, buzzers open again, a longer listen" plus the clue in two sentences at most, then "Let's listen again" — it does not re-read the question.
- Credits (title, composer, performer, license, source) are sent only in `answer.revealed.credit`.

## 7. Act 3 — final

Act gate → category gate → 20 s betting (no question text or choices exposed) → bets lock → question appears and is read (wait for playback) → 20 s private answering (missing = null) → answers lock → simultaneous choice reveal gate → **one `final.bet_revealed` gate per player, ascending by pre-settlement score, ties by seat** (leader last) → suspense → answer gate → settlement gate → `finale.winner` gate → `finale.results` gate → `phase.changed ended`.

Only bets already revealed may appear in snapshots.

## 8. Secrecy (engine side)

The secret list in interface §5 is binding. In addition:

- Snapshots are a strict public projection: no credentials, aliases, explanations, unpublished answers, hidden picks, bet amounts, reading text, output cursors, RNG or audit state. They do include already-public picks/bets and `openGate`.
- **The MC never receives the answer, aliases or explanation before the reveal.** The engine judges; the MC asks and reacts. Reveal-tool results reach the MC only after the gate closes (screen first, MC second).
- `mc.caption` goes through the secret filter (interface §12.2). No captions while a buzzer question is being read. Never caption player speech.
- Phone views are a private projection: a player sees only their own pick/bet.
- Logs record phase and player count only. No answers, names in clear only if needed, never keys.

## 9. Voice: answers, recognition, language

### 9.1 Language (owner decision, 2026-11-26: English only)

- **The game is English only.** The MC speaks English, players speak English, all on-screen text is English. The MC does **not** need to understand Korean. (This overrides the older "players may speak Korean" notes in `interface/KHQS_STAGE_INTERFACE.md`, which is frozen and not edited; it is not a wire change.)
- Player names may be typed in any script; the screen shows them exactly as typed, and the MC says them as given (no nicknames, no honorific suffixes).
- Keep the language rule in configuration and the MC prompt (`server/khqs/mc/prompts.py`), not scattered in code, so another edition can swap content and prompt.

### 9.2 How a spoken answer is captured

Lessons from the prototype's experiments with Gemini native-audio Live:

- Ask the model to call a tool (e.g. `report_answer`) with **`heard`** = the answer exactly as spoken, and **`recognition`** = `clear | unclear`.
- `recognition` means "was the speech understood", **not** "was it correct". The model must not judge correctness.
- Native-audio tool arguments were accurate for short words (6/6 in tests) while the separate input transcription (ASR) was often missing (0/6). **Do not require ASR** to accept an answer.
- Instruct the model to pass `heard` **verbatim, exactly as spoken**, never corrected, completed or reworded toward what it thinks the answer is.
- Require real voiced PCM evidence that the holder actually spoke (energy above a floor) before accepting a voice answer.
- **Recognition failure ≠ wrong answer.** If `recognition` is `unclear`, or the model's wrong answer is not backed by any evidence (no voiced audio / empty transcript where one was expected), treat it as a recognition failure: ask again. After **two** failures, fall back to a text box on that player's phone. Only a supported voice answer or a phone answer is ever judged wrong.
- Tool receipts back to the model are **silent** (do not make the MC speak because a tool returned).

### 9.3 Answer judging (`answer_matches`, deterministic, local)

Normalize (case-fold, strip spaces and punctuation, Unicode NFKC). Then:

1. Exact match against the answer or any alias → correct. (All kinds.)
2. **Music question only (`kind == 'av'`):** also correct if any key of length ≥ 3 is a substring of the heard text, or if a sliding window of the heard text has `difflib.SequenceMatcher` ratio ≥ 0.8 against any key of length ≥ 4. The composer is **not** required; "Danse Macabre" alone is right, "Saint-Saëns Danse Macabre" is right, a one-syllable ASR slip is right.
3. OX, normal buzzer and final questions: exact normalized match only.

Aliases are English (e.g. `Danse Macabre`, `Dance Macabre`; `In the Hall of the Mountain King`, `Hall of the Mountain King`; `Toccata and Fugue in D minor`, `Toccata and Fugue`). The judge still normalises any script, so older Korean aliases would keep working, but none are added.

The voice adapter validates a model-proposed answer with the same function; the model's own opinion of correctness is ignored.

### 9.4 Output playback cursor (reveal timing)

Every MC utterance that precedes a reveal (question reading, suspense line, betrayal prompt) carries an output token. The browser reports the playback position (epoch / sample offset) of the MC audio. The engine advances **only when the matching token has actually finished playing** — not when generation completes. Interrupted tokens become stale. This is what keeps the screen from revealing while the MC is still talking, and the MC from saying a result before the screen shows it.

### 9.5 Audio plumbing

- PCM 16 kHz mono in (mic → Live), 24 kHz out (Live → browser).
- The MC voice plays in the stage page through the host bridge (`KHQS_HOST`, interface §7.1) on the same `AudioContext` the stage uses.
- On a buzz: flush browser MC playback (`stopMc()`) and interrupt Live. Expect Live to send `interrupted` followed by a late `turn_complete`; that order must not be treated as an error (it crashed the prototype once).
- Prototype model: `gemini-3.8-live` (google-genai SDK 2.6.0), voice Despina. Kiro may choose otherwise; keep the cost guard (§11).

## 10. Content (**NEW** work)

- Two question sets of eight, in English, Halloween-themed, cute not gory (no blood, no gore, no jump scares). Questions must be answerable by ear; keep spoken answers short (one to four words) for the buzzer.
- Each question: kind, act number, category, text, answer, explanation, aliases (English; include the common short forms and plain spoken variants), choices (final only).
- Music slot: the three recordings in `media/` (30 s excerpts, tags stripped). Hint clips per level and a private clue per level. Credits exactly as in `docs/HANDOFF.md` §9.
- Category names and question text are drawn on the stage boards: keep categories ≤ ~22 characters and OX/final text ≤ ~110 characters, choices ≤ ~40 characters, and check them on the real stage (`docs/HANDOFF.md` §7 explains how).

## 11. Quota and safety guard for the live MC

The owner runs the Gemini API on the free tier: live runs cost nothing but are limited by quota and rate limits.

- No automatic reconnect loops. A reconnect is an explicit operator action ("Reconnect MC").
- Caps (prototype values, keep or tighten): session 40 min, no input 240 s, response/playback stall 35 s → safe stop; GoAway handled with session resumption, at most 4 times.
- `?mc=mock` (or equivalent) runs the full game with a free mock MC (no voice) for development and tests. Tests must never call the live API.
- The API key is read from the server environment at connect time. It never reaches the browser, logs, the repo, or the stage stream. A public URL must not let strangers start live sessions (they would use up the owner's quota) (see `docs/HANDOFF.md` §8).
