# Kiro Horror Quiz Show — Stage Interface Spec `khqs.stage/1`

Author: visual owner (Claude Code on the Windows PC) · 2026-10-23 · **Status: final v1**
English edition: 2026-11-25, translated from the Korean rev 1.1 (`md5 db9d1d0a…`). The wire format did not change.

**Rev 1.1 (2026-11-08, home-server engine integration):** adds the gate `finale.results`, the reflection event `mc.caption`, and the entry hook `KHQS_ENTRY.reset()`. Existing message fields are unchanged and `proto` stays `khqs.stage/1`. A stage that does not know these types may ignore them (for a gate it answers `beat_done` at once). Details in §12.

> **Status notes (2026-11-25, read these first)**
> - **All on-screen text and the MC voice are English.** Players may speak Korean; the MC understands it and still replies in English. Dynamic strings (names, questions, choices, captions) are drawn by the stage exactly as the engine sends them.
> - **The finale is implemented.** `stage-v3/stage.js` draws the podium finale from `finale.results` (`drawFinale`). §12.1's "temporary finale" wording is history.
> - **`mc.caption` is still not drawn.** The stage logs it only. Drawing captions is optional and belongs to the visual owner, not the engine.
> - **The host bridge and the real-music playback live in the connector, not in the stage.** `stage.js` never reads `window.KHQS_HOST`. See `docs/HANDOFF.md` §5 for the connector contract.
> - **The "main screen is PC Chrome + TV, no subtitles" line in §1 is outdated.** The submission is a standalone web app in a desktop browser.
> - References to `quiz/khqs_v1/…`, `play-link.js` and `docs/KHQS_PLAYABLE.md` point at the earlier prototype (`jarvis-quiz`). That code is a reference only and is not part of the new repository.
> - The wire format is frozen. Do not add fields; the schema uses `additionalProperties: false`.

This is the contract between the engine (server) and the stage (main screen). The engine implements against this spec. The stage was developed first against a mock engine that imitates it.

| File | Contents |
| --- | --- |
| `KHQS_STAGE_INTERFACE.md` | This document (rules and meaning) |
| `stage-protocol.schema.json` | JSON Schema 2020-12. Every message and the scenario file format |
| `scenarios/*.json` | Five mock-engine scenarios (§9) |
| `examples/wire-messages.json` | Final on-the-wire WebSocket examples |
| `tools/validate.py` | Schema validator. `pip install jsonschema`, then `python interface/tools/validate.py` |
| `tools/gen_schema.py` | Schema generator. To change the schema, edit this file, then run `python interface/tools/gen_schema.py interface/stage-protocol.schema.json` |

**The schema is the source of truth for message shape.** If this document and the schema disagree, the schema wins and this document gets fixed.

---

## 1. Settled decisions (2026-10-23)

| # | Decision | Where it lives in this spec |
| --- | --- | --- |
| 1 | Two OX questions **in a row** answered unanimously trigger a betrayal chance. If the lowest score is tied, pick at random. Never call a tied player "last". Ask the reason by voice and offer to switch to the opposite answer | `ox.unanimous.streak`, `betrayal.*`, `selection: "tied_random"` (§6.1) |
| 2 | Buzzer questions hide the text while it is read aloud and **reveal the full text after the reading ends** | `question.presented` with `textHidden: true`, `question.text_revealed` (§6.2) |
| 3 | Buzzing is allowed while music plays. A buzz stops the music at once → spoken answer | `buzzer.pressed.mediaInterrupted`, `stage.media_ended` (§6.3) |
| 4 | Answers, picks and bet amounts never reach the stage before their reveal. Audio/visual assets carry no answer clues | §5 secrecy rules |
| 5 | Gates only at key moments. Keep timeouts and reconnect recovery | §4 gate list (14 types + `finale.results`) |
| 6 | Loss detection uses the **sequence of messages the stage receives**, not the engine's internal event ids | `sseq` (§3.2) |
| - | ~~Main screen is PC Chrome + TV, no subtitles~~ (outdated, see status notes). MC lines come from Live; the engine controls reveal order | §2, §7 |

---

## 2. Connection

- **Transport:** WebSocket, one UTF-8 JSON text frame per message. Suggested path: `/ws/stage`.
- **Location:** the stage runs **inside the same page that plays the MC voice** (one shared `AudioContext`). See the host bridge in §7.
- **Role:** only the one connection whose `stage.hello.role` is `primary` has valid gate replies. Other screens (spectators, a second tab) connect as `viewer`; they get the same stream but their replies are ignored.
- **Version:** every message carries `"proto": "khqs.stage/1"`. Breaking changes move to `khqs.stage/2`. Adding fields inside the same version is not allowed (the schema has `additionalProperties: false`); change this spec first.

### 2.1 Connection order

```
stage  → stage.hello {role, lastSseq, beats, clientTime}
engine → snapshot {sseq = current stream position}       (always start with a snapshot)
engine → stream messages (sseq = snapshot sseq + 1 onward)
stage ↔ stage.ping / pong  (clock sync, every 10 s recommended)
```

---

## 3. Envelope and sequence

### 3.1 Engine → stage

```json
{ "proto": "khqs.stage/1", "type": "ox.choices_revealed", "sseq": 57, "at": 1761300135210,
  "gate": { "id": "g-57", "timeoutMs": 6000 },
  "data": { "choices": [ { "seat": 0, "choice": "O" }, { "seat": 1, "choice": "X" } ] } }
```

- `at`: server time (epoch ms). Every `deadline` is server time too.
- `gate`: present only on gate events. `id` is `"g-" + sseq`. A `gate` on a non-gate event violates the schema.
- Control messages `pong` and `error` are not part of the stream and have no `sseq`.

### 3.2 `sseq` — stage stream sequence (decision 6)

- `sseq` is **the sequence number of stream messages sent to the stage channel in this game**. It is separate from the engine's internal event ids. Internal events that are not sent to the stage do not consume `sseq`.
- It starts at 1 and increases **by exactly 1 with no gaps**. It runs per game and does not reset when the connection changes.
- The engine keeps every stream message it sent together with its `sseq` (for resend and log replay).
- A `snapshot`'s `sseq` is "the last stream position this snapshot reflects". A snapshot does not consume a number.
- Stage rule: if a received `sseq` is not `last + 1`, the stage does not apply it and sends `stage.need_snapshot {lastSseq, receivedSseq}`. The engine answers with a snapshot. An equal or smaller `sseq` (duplicate) is ignored.

### 3.3 Stage → engine

| type | data | Meaning |
| --- | --- | --- |
| `stage.hello` | role, stageVersion, lastSseq, clientTime, beats | Connect / reconnect. `beats` = expected animation length per event (ms) |
| `stage.beat_done` | gate, sseq, skipped? | Gate animation finished. `skipped: true` if it jumped to the rest pose (reconnect etc.) |
| `stage.need_snapshot` | lastSseq, receivedSseq | Sequence gap detected |
| `stage.media_ready` | assetIds | All assets announced at act start are preloaded |
| `stage.media_ended` | assetId, level, reason, positionSec | Music playback ended. `reason`: `ended` / `interrupted` / `error` |
| `stage.ping` | clientTime | Clock sync request (engine answers `pong {clientTime, serverTime}`) |

---

## 4. Gates (decision 5)

After sending a gate event the engine **holds the next gate event** and waits. Reflection events (`ox.submitted`, `mc.status`, …) may still be sent while it waits.

- The stage sends `stage.beat_done` when the animation finishes.
- When `timeoutMs` passes, the engine moves on without waiting. When the next message arrives, the stage fast-forwards the rest of its animation to the rest pose. **A broken stage never stops the game.**
- Only one gate is open at a time. The snapshot's `openGate` holds the currently open gate.

| Gate event | Recommended timeoutMs | Stage animation (roughly) |
| --- | ---: | --- |
| `show.opening` | 60000 | The whole opening (~31 s; 2–3 s if skipped). **MC_READY**: done when the blackout lifts and the ghost stands on the fully lit stage. Only after this reply does the engine cue Gemini's first greeting |
| `act.started` | 8000–10000 | Act sign, lighting change |
| `question.presented` | 5000 | Info board appears |
| `ox.choices_revealed` | 6000 | All paddles flip at once |
| `betrayal.offered` | 6000 | Targeting spotlight (roulette if tied) |
| `betrayal.decided` | 6000 | Paddle flips, or holds |
| `answer.revealed` | 5000–7000 | Drumroll cut → answer board → fanfare / boo |
| `score.settled` | 5000–7000 | Score roll, rank changes |
| `buzzer.judged` | 5000 | Correct / wrong mark |
| `av.hint` | 5000 | More of the picture / gramophone animation |
| `final.category` | 6000 | Category sign |
| `final.choices_revealed` | 7000 | All picks revealed at once |
| `final.bet_revealed` | 6000 | One safe opens (once per player) |
| `finale.winner` | 12000 | Winner animation |
| `finale.results` | 15000 | (1.1) Final standings finale. §12 |

---

## 5. Secrecy rules (decision 4)

The stage channel is a public screen. The items below **must not appear in any message or snapshot before their reveal event.**

| Secret | First sent in |
| --- | --- |
| Correct answer, explanation | `answer.revealed` (afterwards the snapshot carries `revealedAnswer`) |
| OX picks | `ox.choices_revealed` (before that only `ox.submitted {seat}`) |
| Final picks | `final.choices_revealed` (before that only `final.answer_placed {seat}`) |
| Bet amounts | Per-player `final.bet_revealed` (before that only `final.bet_placed {seat}`) |
| Buzzer question text | `question.text_revealed` (after the reading ends) |
| Title / author / performer of an AV asset | `answer.revealed.credit` |
| MC sentences that contain any secret above | Never sent. `mc.caption` goes out only after the engine filters it (§12.2) |

What the schema blocks: a pick in `ox.submitted`, an amount in `final.bet_placed`, or text in a buzzer question's `question.presented` all fail validation.

### 5.1 Audio/visual assets

- The stage knows an asset only by an **opaque id** (`a-` + 8–32 hex chars, e.g. `a-3f9c1d2e7b40`). File paths and URLs must not reveal the answer.
- Suggested route: `GET /stage/assets/{assetId}`. No `Content-Disposition` file name; cacheable.
- Re-encode images to strip EXIF/XMP and other metadata. Strip ID3/Vorbis tags from audio. Do not keep the original file name.
- Credits (title, author, performer, license, source) are kept by the engine and sent only in `answer.revealed.credit`.
- Music must be public domain or CC0 **for both the composition and the recording** (see the status of the three current recordings in `docs/HANDOFF.md`). Level around −16 LUFS.
- `act.started.assets` lists that act's assets (id, kind, size, length). The stage preloads them and sends `stage.media_ready`.

---

## 6. Per-act rules

### 6.1 Act 1 OX and the betrayal chance (decision 1)

```
question.presented(G) → MC reads → phase ox.answering(deadline)
→ ox.submitted {seat} ×n → ox.choices_revealed(G)
→ [if unanimous] ox.unanimous {choice, streak}
→ [if streak ≥ 2] betrayal.offered(G) → betrayal.listening → betrayal.decided(G)
→ answer.suspense → (MC suspense line finishes playing) → answer.revealed(G) → score.settled(G)
```

- `streak` counts consecutive unanimous rounds. When betrayal triggers, the engine resets it to 0 (two more in a row in the same act trigger it again).
- Target: the current lowest score. If the lowest score is tied, pick one at random → `selection: "tied_random"`, candidates in `tiedSeats`.
- Stage: if tied, the spotlight sweeps the candidates like a roulette and stops. **Never write "last", "LAST" or similar.** The engine avoids the same wording in MC instructions.
- `betrayal.decided` with `changed: false` means the player held. The stage starts to flip the paddle and snaps it back.

### 6.2 Act 2 buzzer (decision 2)

```
question.presented(G) {textHidden:true, text:null}
→ phase buzzer.reading + buzzer.armed → MC reads (buzzing allowed meanwhile)
→ [buzz] buzzer.pressed {mcInterrupted:true} → answer → buzzer.judged(G)
→ reading resumes / ends → question.text_revealed {text} → phase buzzer.open
→ ... → answer.revealed(G) → score.settled(G)
```

- A buzzer question's `question.presented` always has `textHidden: true`, `text: null` (enforced by the schema). The info board shows only the category and "listen and answer".
- `question.text_revealed` is sent **after the MC reading has actually finished playing** (by the output playback cursor).
- Progressive text reveal, if ever wanted, is `question.text_progress` in `khqs.stage/2`.
- On `buzzer.pressed` the stage cuts the MC voice at once (host bridge `stopMc()`) and puts a spotlight on that seat. The engine also sends INTERRUPT to Live.
- A wrong answerer goes into `lockedOut`; the stage turns off that seat's buzzer bulb.

### 6.3 Music question (decision 3)

```
question.presented(G) {kind:"av", media:{assetId, mediaType:"audio"}}
→ MC "Let's have a listen" → (actually finishes playing; engine keeps the mic closed)
→ phase buzzer.media + buzzer.armed → av.play {assetId, level, startSec, endSec}
→ [buzz] buzzer.pressed {mediaInterrupted:true}
     → stage: stop the music within 100 ms → stage.media_ended {reason:"interrupted"}
     → engine: open the answer mic after media_ended arrives (wait at most 800 ms)
→ [played to the end] stage.media_ended {reason:"ended"} → phase buzzer.open
→ [all wrong / no answer] av.hint(G) {level} → av.play with a longer clip → ...
```

**Collision rules — required**
1. From `av.play` until `stage.media_ended` the engine **does not let the MC speak and does not forward mic input to Live.** This keeps speaker music from leaking into the mic and confusing the MC (software echo cancellation is off).
2. Music plays only on the stage's question-music bus. The stage guarantees it never sounds at the same time as the MC voice bus.
3. Buzzing is a phone/pad input, so it is accepted while music plays.
4. Picture questions use the same `av.hint` flow, with `media.reveal {mode, amount}` setting how much is shown (`tiles`, `blur`, `zoom`, `silhouette`, `full`). If a different file is needed (silhouette → original), the hint changes `assetId`. (Not used by the current game, which has audio only.)

### 6.4 Act 3 final

```
act.started(G) → final.category(G) → phase final.betting(deadline)
→ final.bet_placed {seat} ×n → final.bets_locked
→ question.presented(G) {choices: 4} → phase final.answering
→ final.answer_placed {seat} ×n → final.answers_locked
→ final.choices_revealed(G)
→ final.bet_revealed(G) × number of players  (order set by the engine: lowest current score first, leader last)
→ answer.suspense → answer.revealed(G) → score.settled(G) → finale.winner(G)
```

- Betting limits and similar rules belong to the engine. The stage animates using only `allIn` (whether it was all in) and `remaining` (score left).
- A tied win is `finale.winner.tie: true` with several seats in `winners`.

---

## 7. Sync with the MC (Gemini Live)

1. **Screen first, MC reacts.** When the MC calls a reveal tool (e.g. `resolve_answer`), the engine sends the gate event and returns the tool result to the MC **only after the gate closes**. The MC can never say a result before the screen shows it.
2. **Suspense is open-ended.** On `answer.suspense` the stage loops a drumroll. When the MC's suspense line has actually finished playing (output cursor), the engine sends `answer.revealed`.
3. **`mc.status`** (`idle` / `speaking` / `listening` / `thinking`) changes the MC puppet's pose. (The stage currently animates the mouth from `mc.status`; real amplitude via `mcOutputNode` is left open.)
4. SFX and music duck automatically while the MC speaks (the stage's job).

### 7.1 Host bridge (an in-page JS interface)

The stage and the MC audio live in the same page, so the host side provides the object below. This is an in-page contract, not a network message.

```js
window.KHQS_HOST = {
  audioContext,                 // the MC audio AudioContext (shared with the stage)
  mcOutputNode,                 // MC voice output node. The stage may attach an AnalyserNode for the mouth
  onMcPlayback(cb),             // cb('start' | 'end') — based on actual playback
  stopMc(),                     // on buzz: flush the MC playback buffer at once
  setMicGate(reason, open),     // a second, stage-side mic block while music plays (reason: 'media')
};
```

The engine's mic open/close rules (by phase) are primary; `setMicGate('media', false)` is the stage-side safety net.

---

## 8. Reconnect and rest pose

- When the stage reconnects with `stage.hello {lastSseq}`, the engine **always** sends a snapshot (resend optimisation is optional).
- On a snapshot the stage draws that phase's **rest pose** with no animation. Revealed answers/picks/bets stay revealed; unrevealed ones stay hidden.
- If the snapshot has `openGate`, the stage draws the rest pose and immediately sends `stage.beat_done {skipped: true}`.
- If a player's phone drops: `seat.connection {connected:false}`. The seat stays `occupied`; the stage freezes the fan and turns its bulbs off.
- Timers are computed by the stage from `deadline` (server time) and the clock offset from `ping/pong`.

---

## 9. Mock engine and scenarios

A scenario file has the schema's `#/$defs/scenario` shape. Each step is one of:

- `{ "delayMs": 300, "send": <engine message>, "note": "…" }` — wait `delayMs` after the previous step, then send. The mock engine fills in `proto`, `sseq`, `at` and `gate.id` (`g-0` in a scenario is a placeholder). If there is a `gate`, it does not move on until `beat_done` or the timeout.
- `{ "await": "stage.media_ended", "timeoutMs": 800 }` — wait for a stage reply.
- `{ "label": "q2" }` — a jump point for the console.

| Scenario | What it checks |
| --- | --- |
| `solo-lobby-opening` | One player joins, two boarded-up empty seats, opening MC_READY gate |
| `duo-act1-ox-betrayal` | Two unanimous rounds in a row, random pick among the tied, answer switch, betrayal pays off |
| `trio-act2-buzzer-music` | Early wrong buzz during reading, full text after reading, buzz stops the music, hint then longer replay, credit reveal |
| `trio-act3-final-allin` | Secret bets, picks revealed, bets revealed one by one (all in), leader drops, comeback win |
| `reconnect-final-midreveal` | Reconnect during the bet reveal, `openGate` handling, disconnected player shown |

Recommended for the engine: export a real game's stage stream in the same scenario format. Then a real game log can be replayed on the stage to find mismatches before integration.

---

## 9.1 Entry desk (lobby → start)

When the stage receives a `phase: lobby` snapshot it draws the lobby (ticket, cast list, name entry, START THE SHOW). Input goes through page-global hooks. If a hook is not defined, the mock engine handles it.

| Hook | Defined in | Contract |
|---|---|---|
| `window.KHQS_ENTRY.join(name)` | stage page | Register a 1–12 character name. Returns `{ ok: true }` or `{ error: 'English message' }`. On success the engine sends `seat.joined` |
| `window.KHQS_ENTRY.start()` | stage page | Start the show. The engine sends `phase.changed opening` and the `show.opening` gate |
| `window.KHQS_JOIN_URL` | stage page | Phone address for the ticket QR. If missing and the page is localhost or a file, the stage shows NO PHONE NEEDED instead of a QR |
| `window.KHQS_TICKET_JOIN(name)` | `ticket.html` | Phone ticket registration. Returns the same as `join` |
| `window.KHQS_ENTRY.reset()` | stage page | (1.1) Close a finished game and open a new lobby. The engine sends a `phase: lobby` snapshot with a new game id. Ignored unless `phase` is `ended` |

(Prior prototype, reference only: `quiz/khqs_v1/play_app.py` served the join/start/reset routes and the phone address and injected a connector script into the stage page.)

## 10. Engine checklist

- [ ] `/ws/stage` WebSocket; `stage.hello` → start with a snapshot
- [ ] Stage-only `sseq` (no gaps, per game, sent messages kept)
- [ ] Test every outgoing message with `check_engine_message()` from `tools/validate.py`
- [ ] 15 gate types: hold the next gate + move on after `timeoutMs`
- [ ] Return MC reveal-tool results only after the gate closes
- [ ] Keep the secrets out of the stage channel and snapshots until their reveal events
- [ ] Buzzer question text in `question.text_revealed` only after the reading has finished playing
- [ ] Music: no MC speech and mic blocked from `av.play` to `stage.media_ended`; on a buzz, open the answer mic only after `media_ended` is confirmed
- [ ] Assets: opaque ids, metadata stripped, credits only in `answer.revealed`
- [ ] `seats` always 3; `fanType` assigned at join and fixed. The schema allows `vampire`, `sack`, `bolt`, `moth`, `fish`, `mummy`, `crone`, `tophat_skull`, **but only `vampire`, `sack`, `bolt`, `tophat_skull` have art — use only those, all different**
- [ ] Betrayal chance: two unanimous in a row, random among the tied, never "last"
- [ ] Final bet reveal order: lowest score first
- [ ] (1.1) `finale.results` gate, then `ended`; `KHQS_ENTRY.reset()` opens a new lobby
- [ ] (1.1) `mc.caption` secret filter (answer, aliases, hidden text)

---

## 12. Rev 1.1 — finale results and MC captions (2026-11-08)

### 12.1 `finale.results` (gate, recommended timeoutMs 15000)

Sent after the `finale.winner` gate closes, followed by `phase.changed ended`. The stage finale must be drawable from **this message alone** (it carries names, fan types, scores and ranks).

```json
{ "type": "finale.results", "gate": {"id": "g-212", "timeoutMs": 15000},
  "data": { "mode": "competitive", "winners": [1], "tie": false,
            "standings": [ {"seat": 1, "playerId": "p-2", "name": "Junho", "fanType": "bolt", "score": 140, "rank": 1, "winner": true},
                           {"seat": 0, "playerId": "p-1", "name": "Mina", "fanType": "sack", "score": 90, "rank": 2, "winner": false} ] } }
```

- `standings`: ascending rank; ties by seat number, sharing the same `rank`. One entry per player (1–3).
- Sent in solo practice too (`mode: solo`); `winners` is that one player. The stage says "SHOW COMPLETE" rather than "WINNER".
- Never use "last", "LAST" or similar in the standings (same rule as §6.1).
- Reconnect: on a `phase: ended` snapshot the stage draws the same finale in rest pose from the snapshot `seats` scores and ranks.
- New game: the finale has a NEW SHOW button that calls `KHQS_ENTRY.reset()` (§9.1). It appears only after the engine signals the end (`finale.results` / ended), so a new show never opens while the MC is still talking.
- ~~The current stage draws a temporary finale.~~ Implemented in `stage-v3` (`drawFinale`: podium, trophy, crown, bouquet, THE END).

### 12.2 `mc.caption` (reflection event, not a gate)

Tells the stage the sentence the MC (Gemini Live) is actually saying. Speech bubbles, captions or keyword emphasis are the visual owner's job; the current stage does not draw them (log only).

```json
{ "type": "mc.caption", "data": { "utteranceId": "u-14", "text": "Shall we open the envelope of fate?", "final": true } }
```

- Messages with the same `utteranceId` are **cumulative** and replace the previous one. `final: true` ends that utterance.
- The source is Live's output audio transcription, which can arrive slightly before the audio plays. The stage paces it while `mc.status` is `speaking`.
- **Secret filter (engine's job):** before the current question's `answer.revealed`, never send a sentence containing the answer, an alias, the correct choice text or the explanation. For one-letter answers (O/X, A–D) block bare symbols such as "the answer is O" and spelled-out forms ("oh / ex"). Once an utterance trips the filter, send nothing more of it (only the safe earlier part already sent).
- Send no captions while a buzzer question is being read (its text is secret until `question.text_revealed`).
- Never caption player speech (answers, reasons). This event covers MC output only.
- A mock MC has no real voice; it sends its progress lines through the same filter.

### 12.3 Engine progression policy (from the prior prototype; keep it)

- A gate closes on **stage `beat_done` + the MC reaction finishing playback**. An engine safety timeout (`timeoutMs` + 25 s) keeps a broken stage or MC from stopping the game. The wire `timeoutMs` is the stage-animation reference value.
- A buzz during the music question waits for `stage.media_ended(interrupted)` but moves on after 800 ms (§6.3).
- Fan types: assign different ones from the four with art: `vampire`, `sack`, `bolt`, `tophat_skull`.
