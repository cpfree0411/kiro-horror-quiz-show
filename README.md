# Kiro Horror Quiz Show

A kitschy, cute Halloween quiz show in the browser. A ghost MC hosts, one to three players answer with their phones, and the stage is a pre-made animated set. Built for the Kiroween hackathon.

**Status: phases P0 to P3 are done.** The show runs end to end on the real stage with either a free mock MC (default) or the Gemini Live voice MC, players on phones or the on-screen pad, and the question bank in a data file. What is left for the next agent: write the real English bank (P4) and package the submission (P5), see "Handoff" below.

## What was made before Kiro, and what was made with Kiro

**Made before Kiro, by the project owner with other AI tools** (Claude Code for stage code, ChatGPT image editing for art plates, Gemini for some music, sound effects from Pixabay):
- the stage (`stage/`): visuals, animation, art, sound design and cues
- the `khqs.stage/1` protocol, its schema, scenarios and validator (`interface/`)
- an earlier private prototype whose lessons are written into `docs/`

**Made with Kiro in this repo:** the engine, server, connector, mock MC, phone UI, question bank, tests and docs written after the handoff. Specs and steering are in [`.kiro/specs`](.kiro/specs) and [`.kiro/steering`](.kiro/steering). This list grows phase by phase.

Kiro did not make the stage or the art.

## Third-party audio

Question music excerpts are in `media/`, with sources and licenses in [`media/CREDITS.md`](media/CREDITS.md) (one recording is CC BY-SA 3.0, two are public domain). Stage sound effects and music cues belong to the frozen stage; its credits are in `stage/CREDITS.md`.

## Ports

| Port | Bind | Serves |
| --- | --- | --- |
| `18830` | `127.0.0.1` only | The stage page, `/ws/stage`, the MC (start, reconnect), every operator action, and everything else. The owner reaches it through an SSH tunnel so the browser sees `localhost` (the microphone needs a secure context). |
| `18831` | the LAN address, default `192.168.50.216` (configurable by setting or environment variable), never `0.0.0.0` | Phone routes only: the ticket page, the phone controller page and its assets, the controller WebSocket, and the join API they use. |

Port `18831` does not serve `/ws/stage`, the stage page, MC start/reconnect or any operator action. This split is a P2 requirement and gets its own test.

Not used by this project and never to be bound: 8814, 18815, 18817, 18818. 

## Run it

```bash
scripts/setup_dev.sh      # once: venv outside the repo + dependencies
scripts/run.sh            # stage on 127.0.0.1:18830, phones on 192.168.50.216:18831, mock MC
KHQS_MC=live scripts/run.sh   # the same with the Gemini Live voice MC (see "Live MC")
```

Open `http://localhost:18830/` in the browser on the machine that shows the stage (the owner's Windows PC reaches it through the SSH tunnel). The lobby shows a QR code for the phone ticket at `http://192.168.50.216:18831/ticket.html`. A phone goes ticket, then ADMITTED, then the controller (`/phone`). Players without a phone type their name on the stage; their controller sits in a collapsible SCREEN PAD panel (an edge tab at the top right, closed unless a pad player has something to do, and visible to everyone in the room). Controllers use select, then LOCK IN.

The bottom-left chip shows PRIMARY or VIEWER, the MC state and the phase. A second tab becomes a viewer; TAKE OVER makes it the primary. NEW SHOW (after the finale, or the chip with a confirmation mid-game) opens a new lobby; question sets alternate between games.

### Settings (environment variables, all optional)

| Variable | Default | Meaning |
| --- | --- | --- |
| `KHQS_STAGE_PORT` | `18830` | stage listener, always on `127.0.0.1` |
| `KHQS_PHONE_HOST` | `192.168.50.216` | the one LAN address for phones (`0.0.0.0`, `::` and empty are refused) |
| `KHQS_PHONE_PORT` | `18831` | phone listener (phone routes only) |
| `KHQS_PUBLIC_PHONE_URL` | `http://<phone host>:<port>/ticket.html` | the URL in the lobby QR |
| `KHQS_BANK` | `banks/dev-bank.json` | question bank file, see `docs/QUESTION_BANK_FORMAT.md`; an invalid file stops startup with a list of errors |
| `KHQS_MC` | `mock` | `mock` or `live` |
| `KHQS_ENV_FILE` | `/home/na/.config/jarvis-live/.env` | file holding `GEMINI_API_KEY`; read only when a live session connects |
| `KHQS_LIVE_MODEL` / `KHQS_LIVE_VOICE` | `gemini-3.8-live` / `Despina` | Live model and voice |
| `KHQS_LIVE_LOG` | none | append one line (time, purpose) per real session opened |
| `KHQS_BUZZER_ANSWER_MS` | `20000` (`60000` with the live MC) | the buzz-in answer window |
| `KHQS_SEED` | random | fix the game seed |

Ports 8814, 18815, 18817 and 18818 belong to other services and are refused.

### Live MC

`KHQS_MC=live` makes the START sign (a) ask the browser for microphone permission, (b) open the audio socket `/ws/mc`, (c) open **one** Gemini Live session, and only then start the show. Failures write `MIC NEEDED` or `MC OFFLINE — TRY AGAIN` in the lobby. The microphone needs a secure context, so use `localhost` (the SSH tunnel). The MC speaks and listens in English only. Spoken answers come back as tool calls with `heard` verbatim; the engine judges them locally, and the model never sees an answer, alias or explanation before the reveal. If the session ends (error, cap, provider GoAway without resumption), the MC goes offline, the show continues with phone typing, and the chip offers RECONNECT MC (an explicit action; there is no automatic reconnect). Caps: 40 minutes per session, 240 s without show activity, 35 s response or playback stall. Free-tier note: each START or reconnect opens one real session.

### Question bank

One JSON file (`docs/QUESTION_BANK_FORMAT.md`). Check a file before using it:

```bash
scripts/check_bank.sh banks/my-bank.json     # ERROR / WARNING lines, exit 1 on errors
KHQS_BANK=banks/my-bank.json scripts/run.sh
```

## Layout

| Path | What |
| --- | --- |
| `stage/` | Frozen stage. Never edited. |
| `interface/` | Frozen protocol spec, schema, scenarios, validator. Never edited. |
| `media/` | Question music excerpts and credits. |
| `docs/` | `HANDOFF.md`, `GAME_RULES.md` (inputs, English-only scope applied), `QUESTION_BANK_FORMAT.md`. |
| `banks/` | Question bank files; `dev-bank.json` is placeholder content. |
| `.kiro/steering/`, `.kiro/specs/` | Kiro steering and per-phase specs. |
| `server/khqs/` | `rules/` (pure), `content/`, `engine/` (state, flow, views; no I/O), `mc/` (mock MC, Live MC, prompts, transport), `server/` (host, apps, connector, MC audio and phone UI in `web/`). |
| `tests/`, `scripts/` | Tests (`tests/support/` is the simulation harness) and dev helpers. |
| `MANIFEST.sha256` | Hashes of every file under `stage/` and `interface/`. |

## Develop

```bash
scripts/setup_dev.sh          # creates the venv outside the repo, installs dev dependencies
scripts/test.sh               # fast tests: manifest, validator, repo hygiene, engine (about 85 s)
scripts/test.sh -m slow       # long browser checks: the stage's #demo, and full games in headless Chromium
sha256sum -c MANIFEST.sha256  # the frozen boundary
python -B interface/tools/validate.py   # expect: ALL OK
```

Play the stage alone: serve `stage/` with any static server (for example `python -m http.server -d stage -b 127.0.0.1 <port>`) and open `index.html#demo`. The stage loads fonts from the internet.

Keep files byte-exact: `.gitattributes` turns off all line-ending conversion, and the manifest check fails on a CRLF change.

## License

Not chosen yet; the owner decides before submission. Plan: MIT for the code written in this repo. `stage/` and `media/` keep their own terms (`stage/CREDITS.md`, `media/CREDITS.md`) and are not relicensed.

## Tests

`scripts/test.sh` runs the fast suite (319 tests, about two minutes). Tests never call the Gemini API; the live MC is tested with a fake transport.

Slow tests (`scripts/test.sh -m slow <file>`, run them in parallel processes): `tests/e2e/test_live_games.py -k players1|players2|players3` (full games in a real browser, 3-5 min each), `tests/e2e/test_live_misc.py` (replay hashes, `#demo`, reload and take-over), `tests/e2e/test_live_mc_browser.py` (a full game through the browser audio host with a fake Live transport), `tests/e2e/test_stage_demo_static.py` (the stage alone), plus `tests/server/test_live_mc.py -k nothing_sent` and `tests/server/test_sockets_and_api.py -k pump_runs`.

`scripts/live_smoke.py` is the one deliberate real-API helper (opens real Live sessions; never run by tests). Evidence from all runs lives outside the repo in `/srv/workdata/build-cache/khqs-evidence/`.

## Handoff (what the next agent does)

1. **P4, the English question bank.** Write `banks/<name>.json` in the documented format (two sets of eight; music slot with the three real recordings in `media/`, hint clips and private clues; English aliases), run `scripts/check_bank.sh`, then check every string on the real stage boards (screenshots at `question.presented`, `question.text_revealed`, `final.choices_revealed`; `docs/HANDOFF.md` §7). Point `KHQS_BANK` at it, or replace `banks/dev-bank.json`.
2. **P5, packaging.** README polish and the disclosure (kept current below), license (the owner plans MIT for code; `stage/` and `media/` keep their own terms), the demo video (the owner), optional public deploy behind the guard in `docs/HANDOFF.md` §8. Never expose the stage listener or the live MC beyond localhost.

Evidence from each phase (screenshots, logs, real-run reports) is in `/srv/workdata/build-cache/khqs-evidence/` on the owner's host; it is not in the repo. Per-phase specs and verification tables: `.kiro/specs/`.

## Known limits

- Memory-only state: restarting the server loses the running game.
- The questions in `banks/dev-bank.json` are placeholders until P4.
- Voice: tested with a fake microphone fed a synthesized "Mirror" clip, not yet with a human voice and room echo. The mic is closed while the MC speaks and during music, because echo cancellation is off by design.
- The MC does not understand other languages (English only, owner decision).
- One live session at a time; the free tier has rate and session limits, so a failed connect is reported, never retried.
- Only the stage page (loopback) can start or reconnect the live MC; the phone port cannot.
- Sound is verified only in headless runs plus the owner's hands-on test of P2 (music and finale worked); the live voice has not been heard by a human yet.
