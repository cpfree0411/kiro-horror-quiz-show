# Kiro Horror Quiz Show

A kitschy, cute Halloween quiz show in the browser. A ghost MC hosts, one to three players answer with their phones, and the stage is a pre-made animated set. Built for the Kiroween hackathon.

**Play it:** <https://khqs.dterrarium.uk> opens the stage (public demo, free mock MC). Join from a phone with the QR code, or open `https://khqs.dterrarium.uk/ticket.html` in a second tab. It is one shared show: the first visitor is the main screen, and an idle game resets after 4 minutes. **Video:** <https://www.youtube.com/watch?v=wVaz8iyPmZY>.

**Status: done (phases P0 to P7).** The show runs end to end on the real stage with either a free mock MC (default) or the Gemini Live voice MC, players on phones or the on-screen pad, and the English question bank `banks/en-bank.json`. The owner played it with the live voice MC: solo games and a two-phone game, the spoken hint request and the spoken yes/no included.

## What was made before Kiro, with Kiro, and alongside Kiro

**Made before the Kiro phase, during the hackathon's submission period (from October 30, 2026), by the project owner with other AI tools** (Claude Code for stage code, ChatGPT image editing for art plates, Gemini for some music, sound effects from Pixabay):
- the stage (`stage/`): visuals, animation, art, sound design and cues
- the `khqs.stage/1` protocol, its schema, scenarios and validator (`interface/`)
- a private prototype built earlier in the hackathon, whose lessons are written into `docs/`

**Made with Kiro in this repo (P0 to P3, P6 and P7):** the engine, server, connector, mock MC, Gemini Live MC, phone UI, the question bank format and loader, the public demo mode and its guards, the soak and leak checks, the Kiro hooks, spoken hints in the music question, tests and docs written after the handoff. How Kiro was used, phase by phase, is in [`docs/KIRO_USAGE.md`](docs/KIRO_USAGE.md). Specs and steering are in [`.kiro/specs`](.kiro/specs) and [`.kiro/steering`](.kiro/steering).

**Made alongside Kiro, by the owner with Claude Code (not by Kiro):**
- the handoff package Kiro started from (`docs/HANDOFF.md`, `docs/GAME_RULES.md`, the frozen `stage/` and `interface/`), and the phase requests sent to Kiro, written from the owner's decisions
- P4: the English question content in `banks/en-bank.json` (questions, explanations, music clues; the three composer names, which Kiro added to the file in P7) and its test `tests/test_en_bank.py`
- one stage change after the handoff, from the owner's play test: the act-2 answer reveal ends on a comedy drum roll (commit `260e0fc`; `MANIFEST.sha256` follows it)
- the public-demo RESTART control, added after the public deployment, including the server action, the stage chip button and tests
- review of each Kiro phase (Claude Code re-ran Kiro's tests and checks), and the P5 packaging: this README pass and `LICENSE`

Kiro did not make the stage, the art, the sound or the question content.

## Kiro features used

- **Specs.** Every Kiro phase started with a spec (requirements, design, tasks) and ended with a `verification.md` that maps each requirement to the test or run that shows it: `.kiro/specs/p0-bootstrap` to `p7-music-hints`.
- **Steering.** Six always-included files in `.kiro/steering/`: the frozen stage contract, secrecy (nothing about an answer reaches the model before its reveal), English-only voice, product, structure and tech. Kiro turned these rules into tests: a manifest check for the frozen files, a leak scanner over every prompt and caption in full games, and sentinel tests for the API key.
- **Agent hooks.** Four in `.kiro/hooks/`:
  - `frozen-boundary` runs the manifest check when `stage/` or `interface/` changes.
  - `bank-check` validates the question banks.
  - `quick-tests` runs a 10-second test subset on code edits.
  - `stop-gate` runs all three when the agent ends a turn.
- **Sub-agent and web search.** The validation sub-agent reviewed P2. A web search checked the Gemini Live model name in P3.
- **Results.** 548 fast tests and 12 slow headless-browser tests. Tests never call the Gemini API; a fake Live transport stands in, and it was made to behave like the real API after the owner's play test found a gap.

The details, with commits, test counts and the bugs verification found, are in [`docs/KIRO_USAGE.md`](docs/KIRO_USAGE.md).

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

### Run it on your own machine

The defaults above fit the owner's home server. On any other machine (Linux or macOS; on Windows use WSL) you need Python 3.12+, [uv](https://docs.astral.sh/uv/), a Chromium-based browser and an internet connection (the stage loads web fonts). No login or credentials are needed.

```bash
git clone https://github.com/cpfree0411/kiro-horror-quiz-show
cd kiro-horror-quiz-show
export KHQS_VENV="$HOME/.venvs/khqs" KHQS_UV_CACHE="$HOME/.cache/uv"   # the default venv path only exists on the owner's server
scripts/setup_dev.sh
KHQS_PHONE_HOST=<this computer's LAN IP> scripts/run.sh                # free mock host, no API key
```

Open `http://localhost:18830/` on the same computer (full screen looks best).

- **Join with a phone** on the same Wi-Fi: scan the QR code in the lobby, enter a name, GET IN.
- **Join without a phone:** type a name on the stage; that player uses the on-screen SCREEN PAD (the edge tab at the top right). `KHQS_PHONE_HOST` must still be a LAN address even then (loopback is refused).
- Use two players to see the Betrayal Chance (act 1) and the hint vote (the act-2 music question). Press START; the mock host needs no microphone, so answer by tapping or typing.

**Live voice host (optional, your own Gemini API key):**

```bash
echo "GEMINI_API_KEY=your-key" > ~/khqs.env
KHQS_MC=live KHQS_ENV_FILE=~/khqs.env KHQS_PHONE_HOST=<LAN IP> scripts/run.sh
```

Open the stage at `http://localhost:18830/` (the microphone needs `localhost`), allow the microphone and speak English. Each START opens one Gemini Live session. Try buzzing in the music question and saying "It's too hard, give me a hint!"

### Settings (environment variables, all optional)

| Variable | Default | Meaning |
| --- | --- | --- |
| `KHQS_STAGE_PORT` | `18830` | stage listener, always on `127.0.0.1` |
| `KHQS_PHONE_HOST` | `192.168.50.216` | the one LAN address for phones (`0.0.0.0`, `::` and empty are refused) |
| `KHQS_PHONE_PORT` | `18831` | phone listener (phone routes only) |
| `KHQS_PUBLIC_PHONE_URL` | `http://<phone host>:<port>/ticket.html` | the URL in the lobby QR |
| `KHQS_BANK` | `banks/en-bank.json` (set by `scripts/run.sh`; without it the server uses the dev bank) | question bank file, see `docs/QUESTION_BANK_FORMAT.md`; an invalid file stops startup with a list of errors |
| `KHQS_MC` | `mock` | `mock` or `live` |
| `KHQS_ENV_FILE` | `/home/na/.config/jarvis-live/.env` | file holding `GEMINI_API_KEY`; read only when a live session connects |
| `KHQS_LIVE_MODEL` / `KHQS_LIVE_VOICE` | `gemini-3.8-live` / `Despina` | Live model and voice |
| `KHQS_LIVE_LOG` | none | append one line (time, purpose) per real session opened |
| `KHQS_BUZZER_ANSWER_MS` | `20000` (`60000` with the live MC) | the buzz-in answer window |
| `KHQS_SEED` | random | fix the game seed |
| `KHQS_PUBLIC`, `KHQS_PUBLIC_HOST`, `KHQS_OPERATOR_SECRET_FILE` | off | public demo mode behind a tunnel, see `docs/PUBLIC_DEMO.md` |
| `KHQS_DIAG` | off | `1` enables `GET /api/diag` (process and table sizes) for the soak runs; local only |

Ports 8814, 18815, 18817 and 18818 belong to other services and are refused.

### Live MC

`KHQS_MC=live` makes the START sign (a) ask the browser for microphone permission, (b) open the audio socket `/ws/mc`, (c) open **one** Gemini Live session, and only then start the show. Failures write `MIC NEEDED` or `MC OFFLINE — TRY AGAIN` in the lobby. The microphone needs a secure context, so use `localhost` (the SSH tunnel). The MC speaks and listens in English only. Spoken answers come back as tool calls with `heard` verbatim; the engine judges them locally, and the model never sees an answer, alias or explanation before the reveal. If the session ends (error, cap, provider GoAway without resumption), the MC goes offline, the show continues with phone typing, and the chip offers RECONNECT MC (an explicit action; there is no automatic reconnect). Caps: 40 minutes per session, 240 s without show activity, 35 s response or playback stall. Free-tier note: each START or reconnect opens one real session.

### Hints in the music question

The clip gets longer after a failed level by itself (levels 0 to 2, one short MC line, no clue). Spoken hints come only on request: a player who holds the buzzer says "give me a hint" (the MC reports the words, the engine decides) or taps HINT? on the phone. With other players present the MC asks them, the engine opens an 8 s window, they say or tap yes or no (any refusal refuses; silence counts as yes), and then the MC gives clue 1, clue 2 or the composer. The requester answers at once; right is +20, wrong locks out as usual. Each player may ask once, at most three hints per question. Rules: `docs/GAME_RULES.md` §6.2. Each track in a bank needs a `composer` (`docs/QUESTION_BANK_FORMAT.md`).

### Public demo mode

`docs/PUBLIC_DEMO.md` explains how the show can sit behind a tunnel: visitors get the stage, phones and the mock MC only; operator actions and the live MC need the operator secret from a local request; one game at a time with the §11 caps; per-address rate limits. Nothing is deployed from this repo; the owner runs one at <https://khqs.dterrarium.uk> (a pinned copy of this repo on the home server, behind a Cloudflare tunnel, mock MC only) through the end of judging.

### Question bank

One JSON file (`docs/QUESTION_BANK_FORMAT.md`). Check a file before using it:

```bash
scripts/check_bank.sh banks/my-bank.json     # ERROR / WARNING lines, exit 1 on errors
KHQS_BANK=banks/my-bank.json scripts/run.sh
```

## Layout

| Path | What |
| --- | --- |
| `stage/` | Frozen stage. Never edited by Kiro; one later sound change by Claude Code (`260e0fc`). |
| `interface/` | Frozen protocol spec, schema, scenarios, validator. Never edited. |
| `media/` | Question music excerpts and credits. |
| `docs/` | `HANDOFF.md`, `GAME_RULES.md` (inputs, English-only scope applied), `QUESTION_BANK_FORMAT.md`. |
| `banks/` | Question bank files; `en-bank.json` is the show bank; `dev-bank.json` is placeholder content kept for tests. |
| `.kiro/steering/`, `.kiro/specs/` | Kiro steering and per-phase specs. |
| `server/khqs/` | `rules/` (pure), `content/`, `engine/` (state, flow, views; no I/O), `mc/` (mock MC, Live MC, prompts, transport), `server/` (host, apps, connector, MC audio and phone UI in `web/`). |
| `tests/`, `scripts/` | Tests (`tests/support/` is the simulation harness) and dev helpers. |
| `MANIFEST.sha256` | Hashes of every file under `stage/` and `interface/`. |

## Develop

```bash
scripts/setup_dev.sh          # creates the venv outside the repo, installs dev dependencies
scripts/test.sh               # fast tests: manifest, validator, repo hygiene, engine, server (about four minutes)
scripts/test.sh -m slow       # long browser checks: the stage's #demo, and full games in headless Chromium
sha256sum -c MANIFEST.sha256  # the frozen boundary
python -B interface/tools/validate.py   # expect: ALL OK
```

Play the stage alone: serve `stage/` with any static server (for example `python -m http.server -d stage -b 127.0.0.1 <port>`) and open `index.html#demo`. The stage loads fonts from the internet.

Keep files byte-exact: `.gitattributes` turns off all line-ending conversion, and the manifest check fails on a CRLF change.

## License

The code in this repository (server, scripts, tests, the stage code in `stage/` and the protocol in `interface/`) is under the [MIT License](LICENSE). What it does not cover is listed here and in [NOTICE.md](NOTICE.md). Third-party media keep their own licenses and are not relicensed:
- `media/`: question music, listed in `media/CREDITS.md` (one recording CC BY-SA 3.0, two public domain).
- `stage/assets/sound/`: sound effects from Pixabay under the Pixabay Content License, listed in `stage/CREDITS.md`; they may not be redistributed on their own.

The art in `stage/assets/` and the Gemini-generated music cues were made by the owner for this project and are not under the MIT License; they may be used to run, review and judge the project.

## Tests

`scripts/test.sh` runs the fast suite (about three to four minutes). Tests never call the Gemini API; the live MC is tested with a fake transport.

Slow tests (`scripts/test.sh -m slow <file>`, run them in parallel processes): `tests/e2e/test_live_games.py -k players1|players2|players3` (full games in a real browser, 3-5 min each), `tests/e2e/test_live_misc.py` (replay hashes, `#demo`, reload and take-over), `tests/e2e/test_live_mc_browser.py` (a full game through the browser audio host with a fake Live transport), `tests/e2e/test_stage_demo_static.py` (the stage alone), plus `tests/server/test_live_mc.py -k nothing_sent` and `tests/server/test_sockets_and_api.py -k pump_runs`.

`scripts/soak.py` runs soak and robustness checks against a real server in its own process: `games 30` (back-to-back games through NEW SHOW), `storm` (phone and stage reconnect storms), `idle 3600 [public]`. `scripts/test_quick.sh` is the ten-second subset the Kiro hooks run (`.kiro/hooks/`, see `docs/KIRO_USAGE.md`); `scripts/check_manifest.sh` and `scripts/check_banks.sh` are the other two hook scripts.

`scripts/live_smoke.py` is the one deliberate real-API helper (opens real Live sessions; never run by tests). Evidence from all runs lives outside the repo in `/srv/workdata/build-cache/khqs-evidence/`.

## Handoff (what the next agent does)

1. **P4, the English question bank: done.** `banks/en-bank.json` (two sets of eight, three music tracks), checked with `scripts/check_bank.sh` (0 errors, 0 warnings) and on the real stage boards; act-2 explanations are short because the stage draws them as the big answer card.
2. **P5, packaging: done by Claude Code.** This README pass, the disclosure above and `LICENSE`. Done by the owner outside Kiro: the demo video, and the public demo at <https://khqs.dterrarium.uk> set up as `docs/PUBLIC_DEMO.md` describes. Never expose the stage listener or the live MC beyond localhost.

Evidence from each phase (screenshots, logs, real-run reports) is in `/srv/workdata/build-cache/khqs-evidence/` on the owner's host; it is not in the repo. Per-phase specs and verification tables: `.kiro/specs/`.

## Known limits

- Memory-only state: restarting the server loses the running game.
- Voice: tested by the owner with a human voice in one room (English). The mic is closed while the MC speaks and during music, because echo cancellation is off by design. Several people talking at once in the hint vote has not been tried.
- The MC does not understand other languages (English only, owner decision).
- One live session at a time; the free tier has rate and session limits, so a failed connect is reported, never retried.
- Only the stage page (loopback) can start or reconnect the live MC; the phone port cannot.
- Play tests: the owner's live-voice games on 2026-11-27 (solo games and a two-phone game) covered the betrayal offer, the spoken hint request, the hint vote and the finale; every MC line in those runs produced audio. Larger groups and long sessions have only been tested with the mock MC (`scripts/soak.py`).
