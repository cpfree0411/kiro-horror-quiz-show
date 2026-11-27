# Kiro Horror Quiz Show — Handoff to Kiro

Status: 2026-11-25. From: the visual/sound owner. To: Kiro (engine, AI MC, multiplayer, integration).
**Scope change (owner, 2026-11-26): the game is English only. Players speak English and the MC does not need to understand Korean.** Where older text here or in `interface/KHQS_STAGE_INTERFACE.md` says otherwise, this note wins.

Read in this order: this file → `docs/GAME_RULES.md` → `interface/KHQS_STAGE_INTERFACE.md` → `interface/stage-protocol.schema.json`.

---

## 1. What exists and what Kiro builds

**Already made (frozen, reused as is):** the whole visual and sound show — the browser stage (`stage/`), its art, animation, transitions, opening, lobby, finale, sound effects and music cues, plus the wire protocol `khqs.stage/1` (spec, JSON Schema, scenarios, validator). These were made before Kiro joined, by the project owner with other AI tools (Claude Code for stage code, ChatGPT image editing for art plates, Gemini for some music; sound effects from Pixabay).

**Kiro builds (new code in this repo):**

1. The authoritative game engine (rules in `docs/GAME_RULES.md`).
2. The server: stage WebSocket, phone/controller WebSocket, entry API, asset route, page serving with connector injection.
3. The connector script that plugs the real engine into the frozen stage (§5).
4. The phone ticket hook and the phone controller UI; the on-screen pad for players without a phone.
5. The AI MC: Gemini Live voice host (English in, English out), with a free mock MC for development.
6. The English question bank (two sets of eight) and the music question data.
7. Tests, a headless end-to-end driver, the run script, the README and submission notes.

An earlier private prototype (`jarvis-quiz`, not in this repo) already proved most of this. Its lessons are written into these docs. **Write the new engine fresh in this repo; do not copy prototype code.** If anything is ever copied or ported, say so in the README.

---

## 2. Repository layout (proposed)

```
/                       repo root
├─ stage/               FROZEN — the stage (copied from stage-v3)
├─ interface/           FROZEN — protocol spec, schema, scenarios, examples, validator
├─ media/               the three music excerpts (30 s MP3, tags stripped) + CREDITS
├─ docs/                HANDOFF.md, GAME_RULES.md (+ Kiro's own design notes)
├─ .kiro/steering/      product, stage contract, language, secrecy & safety
├─ .kiro/specs/         Kiro writes these (requirements / design / tasks)
├─ server/ (or src/)    Kiro: engine, server, MC adapter, connector, phone UI
├─ tests/               Kiro
├─ MANIFEST.sha256      hashes of every file under stage/ and interface/
└─ README.md            Kiro writes; must include the disclosure in §10
```

The language/framework of the server is Kiro's choice. The prototype used Python (asyncio, Starlette/Uvicorn-style ASGI, `google-genai`), which is a proven fit: one event loop, one worker, server-owned clock.

---

## 3. The frozen boundary

| Path | Rule |
| --- | --- |
| `stage/**` | **Do not edit.** No refactors, no reformatting, no "small fixes", no new files. The server serves these bytes and injects one script tag at serve time (§5.1). |
| `interface/**` | **Do not edit.** The schema is the wire truth (`additionalProperties: false`). Do not add fields. |
| `MANIFEST.sha256` | A test must verify it (`sha256sum -c MANIFEST.sha256` or equivalent). A mismatch fails CI. |

Not Kiro's to reinterpret: the opening sequence and its timing, the lobby/registration look, act transitions, character animation, verdict badges, finale, music/SFX cue timing. The stage decides how things look and sound; the engine decides **what happens and when** via the protocol.

If the stage really cannot do something the game needs, stop and write it up (file `docs/STAGE_REQUESTS.md`: what, why, which message). The visual owner changes the stage and ships a new manifest. Do not work around it inside `stage/`.

Known stage limits that are **accepted** (do not fix):
- `mc.caption` is logged, not drawn.
- The ghost's mouth follows `mc.status`, not real voice amplitude.
- Stage code comments and the stage README are being translated to English by the visual owner; a new manifest will come with that. Treat comment language as irrelevant.

---

## 4. Responsibilities

| Concern | Owner | Notes |
| --- | --- | --- |
| Rules, scoring, timers, phases, judging | Engine | Deterministic, server clock, seeded RNG. Never a model |
| What is secret and when it is revealed | Engine | Interface §5, rules §8 |
| Reveal order and timing | Engine | Gates + MC output playback cursor |
| Speaking, listening, reacting, pacing jokes | MC (Gemini Live) | Never sees answers before reveal; never decides correctness |
| Capturing a spoken answer | MC → tool call → engine | `heard` verbatim + `recognition`; engine judges with `answer_matches` |
| Drawing, animation, SFX, music cues | Stage (frozen) | Driven only by protocol messages |
| Playing the question music | Connector | Real asset on the question-music bus (§5.3) |
| MC audio in the page, mic capture | Connector + host bridge | `window.KHQS_HOST` (interface §7.1) |
| Join / start / new show | Connector → server API | `window.KHQS_ENTRY` hooks |
| Phone ticket, phone controller, screen pad | Kiro (new UI) | English UI; looks like the show (see §6) |
| Operator controls (MC status, reconnect MC, new game) | Connector | Outside the 16:9 stage area; English |

---

## 5. The connector contract

The stage was written against a mock engine. The connector swaps in the real one **without touching stage files**.

### 5.1 Injection

`stage/index.html` loads, in order:

```
assets/manifest.js → scenarios.js → sound-files.js → sound.js → mock-engine.js → qr.js → assets/opening-art.js → stage.js
```

When the server serves `index.html` for a live show, it inserts **one** `<script src="/play/link.js"></script>` (path is Kiro's choice) **right after `mock-engine.js`** and before `stage.js`. Serve the file from disk otherwise unchanged. Do the same for `ticket.html` with a ticket hook script.

### 5.2 Replace `window.MockEngine` with the same shape

`stage.js` does `new MockEngine({ deliver, log })` and only uses this surface:

| Member | Stage uses it for | Real engine should |
| --- | --- | --- |
| `constructor({deliver, log})` | `deliver(msg, {fast})` = engine → stage; `log(kind, msg)` = protocol log panel | Keep both |
| `receive(msg)` | every stage → engine message (`stage.beat_done`, `stage.media_ended`, …) | Send over the WebSocket (queue until open). Viewers must not forward `beat_done` / `media_*` |
| `load(scenario)`, `start(label)` | boot / act select | `start()` opens the WebSocket (or asks for a snapshot if already open). `load()` is a no-op |
| `stop()`, `labels()`, `speed`, `paused`, `run`, `scenario` | HUD / replay | Harmless no-ops / defaults |
| `send(...)`, `sleep(...)` | the stage's own mock lobby and `#demo` | No-op (entry goes through `KHQS_ENTRY`) |

On every incoming message: drop `pong`; handle `error`; drop stream messages with `sseq <= last`; then `deliver(msg, {fast: false})`. On `buzzer.pressed`, call `KHQS_HOST.stopMc()` at once. On `act.started`, start fetching the listed assets. Send `stage.ping` every 10 s. Reconnect on close (1 s backoff) with `stage.hello {lastSseq}`. If a primary is already connected, fall back to `viewer` and show that in the operator chip.

`stage.beat_done` must carry `sseq` (the numeric part of `g-<sseq>`); the stage already sends it.

### 5.3 Real music: hijack `Sound.loop('waltz')`

On `av.play` the stage shows the gramophone, times the clip itself (`endSec − startSec`) and calls `Sound.loop('waltz', true)`; on a buzz or the end it calls `Sound.loop('waltz', false)` and sends `stage.media_ended`. The placeholder waltz is synthetic. The connector wraps `Sound.loop` so that `'waltz'` on → fetch `/stage/assets/{assetId}`, decode, play `[startSec, endSec]` on the shared `AudioContext`, and `setMicGate('media', false)`; `'waltz'` off → stop the source and reopen the mic gate. All other loop names pass through.

### 5.4 Placeholder voice chirp

The stage plays a small `voice` SFX as a stand-in for the MC. With the live MC, the connector wraps `Sound.cue` to drop `'voice'` (the real voice replaces it). Keep it with the mock MC.

### 5.5 Entry hooks and host bridge

- `window.KHQS_ENTRY = { join(name), start(), reset(force) }` → POST to the server.
  - `join` returns `{ok:true}` or `{error:'SHORT ENGLISH MESSAGE'}`; the stage prints the error under the name box itself.
  - `start()` has no return contract. In live mode it gets mic permission and opens the MC audio first. On failure the connector writes `MIC NEEDED` / `MC OFFLINE — TRY AGAIN` into the lobby's `.lb-err` element and re-enables `.lb-start` (the prototype did this; those class names are part of the frozen stage).
  - `reset()` returns `{ok:true}` when a new lobby exists. The stage plays the bat transition and waits up to 4 s for the new `phase: lobby` snapshot.
- `window.KHQS_JOIN_URL` = the phone ticket URL for the QR (unset → the stage shows NO PHONE NEEDED on localhost).
- `window.KHQS_TICKET_JOIN(name)` in `ticket.html` → same result shape as `join`. It must be defined **before** the ticket page's inline script runs, so inject the ticket hook in `<head>`. Without it the ticket falls back to a same-origin `BroadcastChannel` demo.
- `window.KHQS_HOST` = interface §7.1, created by the connector when the MC audio starts. The stage itself never reads it.

### 5.6 Leave the replay modes alone — **trap**

The stage has built-in replay/demo modes driven by the URL hash. The connector must **not** take over when any of these is present: `act=`, `step=`, `opening`, `showtime`, `clean`, `verdict=`, `demo`, `finale=`, `trans=`. (The prototype's connector forgot `demo`, `finale=` and `trans=`.) Modifiers that may appear with them: `cast=`, `stay`, `qr=`, `still`, `stuck`, `badge=`.

---

## 6. Phone and screen controller (Kiro's UI)

- English only. Big touch targets. Works on a phone browser without install.
- Screens: ticket (name → GET IN → admitted) → waiting → OX (O / X) → buzzer (BUZZ) → betrayal (reason button, KEEP / SWITCH) → answer text box (after two voice-recognition failures, or when typing is chosen) → final bet (slider/number within `[0, score]`) → final choice (A–D) → done.
- Each player sees only their own pick and bet. Show the deadline countdown from server time.
- The on-screen pad (players without a phone) is a development/demo aid: it is visible to everyone, so say so in its label.
- Visual tone: match the show (dark wood, warm bulbs, cream paper, Alfa Slab One / Fredoka). Do not import stage files into the phone page beyond fonts; the stage CSS uses absolute positioning that breaks controller layouts (it broke the prototype's pad).

---

## 7. Stage modes you can use while building

Serve `stage/` statically (any static server; fonts need internet) and open `index.html` with:

| Hash | What it does |
| --- | --- |
| `#demo` | Full unattended show, lobby → opening → act 1 → act 2 → act 3 → finale (~5 min). Sets `window.KHQS_showDone` at the end |
| `#opening` (`&clean` auto-joins two names and starts; `&cast=A,B`; `&stay`) | The opening only, ending at MC_READY |
| `#act=1` / `#act=2` / `#act=3` | Replays that act's scenario through the mock engine; HUD lets you pause, restart, jump |
| `#act=N&step=K&clean` | Freeze just before step K, HUD hidden (screenshots) |
| `#act=3&finale=1` (`2`, `3`, `tie`; `&still`) | Finale for 1/2/3 players or a tie |
| `#act=1&trans=act&clean` | Act transition preview |

The protocol log panel (`L`) shows every message in and out. To check that new English questions fit the boards, run a mock-MC game with the real engine and take screenshots at each `question.presented`, `question.text_revealed` and `final.choices_revealed`; compare with the stills the stage produces in `#act=N` replays.

---

## 8. Running, environment, quota guard

- Target host: the project owner's Ubuntu home server, where Kiro CLI runs. Machine-specific paths, ports and the key location are in the start prompt, not in this repo.
- The Gemini API key is read from an environment file **outside the repo** at the moment the MC connects. Never commit it, log it, print it, send it to the browser, or copy it into the repo.
- Microphone capture needs a secure context: `localhost` (e.g. through an SSH tunnel) or HTTPS.
- **Public URL guard (required if the show is ever exposed beyond the LAN):** starting a live MC session must need an operator secret or be bound to localhost; one live session at a time; the caps in `GAME_RULES.md` §11; a mock-MC public mode is fine. Strangers must not be able to use up the API quota.
- Tests and CI never call the live API. The owner uses the Gemini free tier, so a deliberate real smoke run is fine when a phase needs it; mind the rate limits.
- Do not touch other services on the host. Pick unused ports and say which ones in the README.

---

## 9. Audio assets and licenses

Question music (`media/`, 30 s excerpts, tags stripped, served only by opaque id):

| File | Work | Recording | License |
| --- | --- | --- | --- |
| `bwv565.mp3` | J. S. Bach — Toccata and Fugue in D minor, BWV 565 | Wikipedia user "Cor anglais 16" (Flentrop organ, Oberlin Conservatory) | Composition PD; recording **CC BY-SA 3.0** (dual GFDL). Excerpt, trimmed. Source: https://commons.wikimedia.org/wiki/File:BWV-565-intro.ogg |
| `danse_macabre.mp3` | Camille Saint-Saëns — Danse macabre, Op. 40 | Philadelphia Orchestra, cond. Leopold Stokowski (Victor 6505, recorded 1925-04-29, early electrical) | Composition PD; recording **public domain in the US** (PD-US-record-expired: published 1925, US public domain since 2026-01-01) and expired elsewhere. Excerpt from 25.8 s, trimmed and level-matched. Source: https://commons.wikimedia.org/wiki/File:PhiladelphiaSymphonyOrchestra-DanseMacabre.ogg |
| `mountain_king.mp3` | Edvard Grieg — In the Hall of the Mountain King (Peer Gynt Suite No. 1, Op. 46) | Czech National Symphony Orchestra (for Musopen) | Public domain (released by Musopen). Source: https://commons.wikimedia.org/wiki/File:Musopen_-_In_the_Hall_Of_The_Mountain_King.ogg |

- The CC BY-SA excerpt needs attribution and the same license for the excerpt itself; put the credits in `media/CREDITS.md` and the README.
- The Danse Macabre recording was replaced on 2026-11-26 (the earlier 1953 Fourestier recording is likely still protected in the US). The new excerpt covers the same passage (theme entry after the opening) at the same loudness (−19.6 LUFS).
- Stage sound effects and music cues (Pixabay Content License items and Gemini-generated tracks) are part of the frozen stage; the visual owner supplies a `stage/CREDITS.md`.

---

## 10. Submission honesty (README disclosure)

The README must say plainly:
- **Made before the Kiro phase, during the hackathon's submission period (from October 30, 2026), by the project owner with other AI tools:** stage visuals and animation, art, sound design and cues, the `khqs.stage/1` protocol and its scenarios, and a private prototype built earlier in the hackathon, whose lessons are written into `docs/`.
- **Made with Kiro in this repo:** the engine, server, connector, MC integration, phone UI, question bank, tests and docs Kiro wrote (with links to `.kiro/specs` and steering).
- Third-party audio credits (§9).

Never claim Kiro made the stage or the art. Check the hackathon's official rules for anything else required (license, video length, `.kiro` folder kept in the repo, category) — this handoff does not restate them.

---

## 11. Plan and acceptance criteria

Each phase ends with evidence: commands run, test output, and for browser phases screenshots/frames. "Worker finished" is not acceptance.

**P0 — Repo bootstrap**
- Copy `stage/`, `interface/`, `media/`, `docs/`, `.kiro/steering/`; add `MANIFEST.sha256` check as a test.
- Accept: manifest check passes; `python interface/tools/validate.py` → ALL OK; `stage/index.html#demo` plays statically.

**P1 — Engine core (no network, no model)**
- All rules in `GAME_RULES.md`; fake clock; seeded RNG; every outgoing message validated with `interface/tools/validate.py` (`check_engine_message`).
- Behaviour tests for each of the five scenario themes (solo opening, duo betrayal, trio buzzer + music + hint, trio all-in final, reconnect mid-reveal), plus: gate id + sseq matching, duplicate/stale acks harmless, settlement exactly once, snapshot projection has no secrets.
- Accept: test suite green; a secrecy scan over every emitted stream finds no answer/pick/bet/text before its reveal.

**P2 — Server, connector, phones, mock MC**
- `/ws/stage`, controller WebSocket, entry API, `/stage/assets/{id}`, page serving with injection (§5.1), connector (§5.2–5.6), ticket + phone UI, screen pad, operator chip, mock MC with the same playback-cursor contract.
- Accept: headless-browser full games with the mock MC for 1, 2 and 3 players (one using the screen pad, one phone reload mid-game) complete; stage role is `primary` and acks gates; page errors 0; `#demo` still plays as a mock on the live server; stream secrecy scan clean.

**P3 — Gemini Live MC**
- English host persona (English in, English out); tool-based answer capture (`heard` verbatim + `recognition`); two retries then phone text box; output playback cursor gating; buzz → flush + interrupt; music → MC idle + mic closed; betrayal reason/decision by voice or phone; `mc.caption` with the secret filter; caps and no automatic reconnect; mock MC unchanged.
- Accept: unit tests with a fake Live session; a real end-to-end smoke run (free tier, run deliberately); then the owner plays it with a real voice (English answers). Record what was and was not verified.

**P4 — English content**
- Two English sets of eight (rules §10), music slot with hint clips and private clues, English aliases.
- Accept: every string checked on the real stage boards (screenshots), aliases tested with `answer_matches`.

**P5 — Submission**
- README with run steps, ports, disclosure (§10), credits (§9), license; optional public deploy behind the guard (§8); the demo video is recorded by the project owner.
- Accept: a clean clone + documented steps runs a mock game; manifest check passes.

---

## 12. Traps the prototype hit

1. Live sends `interrupted` and then a late `turn_complete` after a barge-in. Treat as normal, not as an error.
2. Native-audio tool args are reliable for short answers; separate ASR transcripts are often missing. Do not require ASR.
3. The model "helpfully" corrects or completes an answer unless told to report `heard` verbatim.
4. The buzzer answer window must be long enough for a retry and the phone fallback; the public `deadline` must match the real window.
5. Stage CSS `.choice { position: absolute }` leaks into any controller placed in the stage page. Scope controller styles.
6. A second stage tab must become a `viewer`, not steal `primary`. Reconnecting the primary is an explicit operator action.
7. Memory-only state: a server restart loses the game. Acceptable for the show; say so in the README.
8. Names typed in another script may be pronounced oddly. That is fine; the screen always shows the name exactly as typed. Give the MC the names as typed and forbid nicknames or honorific suffixes.
9. Generation finished ≠ audio played. Gate reveals on the playback cursor only.
