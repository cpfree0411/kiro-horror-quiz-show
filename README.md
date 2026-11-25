# Kiro Horror Quiz Show

A kitschy, cute Halloween quiz show in the browser. A ghost MC hosts, one to three players answer with their phones, and the stage is a pre-made animated set. Built for the Kiroween hackathon.

**Status: phase P0 (repo bootstrap).** The engine, server, MC and phone UI do not exist yet. What works today is the frozen stage played on its own (see below).

## What was made before Kiro, and what was made with Kiro

**Made before Kiro, by the project owner with other AI tools** (Claude Code for stage code, ChatGPT image editing for art plates, Gemini for some music, sound effects from Pixabay):
- the stage (`stage/`): visuals, animation, art, sound design and cues
- the `khqs.stage/1` protocol, its schema, scenarios and validator (`interface/`)
- an earlier private prototype whose lessons are written into `docs/`

**Made with Kiro in this repo:** the engine, server, connector, MC integration, phone UI, question bank, tests and docs written after the handoff. Specs and steering are in [`.kiro/specs`](.kiro/specs) and [`.kiro/steering`](.kiro/steering). This list grows phase by phase.

Kiro did not make the stage or the art.

## Third-party audio

Question music excerpts are in `media/`, with sources and licenses in [`media/CREDITS.md`](media/CREDITS.md) (one recording is CC BY-SA 3.0, two are public domain). Stage sound effects and music cues belong to the frozen stage; its credits are in `stage/CREDITS.md`.

## Ports

| Port | Bind | Purpose |
| --- | --- | --- |
| `18830` | `127.0.0.1` | Stage page, stage WebSocket, MC. The owner reaches it through an SSH tunnel so the browser sees `localhost` (microphone needs a secure context). |
| `18831` | LAN interface | Phone controllers and the ticket page. |

Not used by this project and never to be bound: 8814, 18815, 18817, 18818. Nothing listens on 18830/18831 yet; the server arrives in P2.

## Layout

| Path | What |
| --- | --- |
| `stage/` | Frozen stage. Never edited. |
| `interface/` | Frozen protocol spec, schema, scenarios, validator. Never edited. |
| `media/` | Question music excerpts and credits. |
| `docs/` | `HANDOFF.md`, `GAME_RULES.md` (inputs) and later design notes. |
| `.kiro/steering/`, `.kiro/specs/` | Kiro steering and per-phase specs. |
| `tests/`, `scripts/` | Tests and dev helpers. |
| `MANIFEST.sha256` | Hashes of every file under `stage/` and `interface/`. |

## Develop

```bash
scripts/setup_dev.sh          # creates the venv outside the repo, installs dev dependencies
scripts/test.sh               # fast tests: manifest, validator, repo hygiene
scripts/test.sh -m slow       # the 5-minute static #demo run in headless Chromium
sha256sum -c MANIFEST.sha256  # the frozen boundary
python -B interface/tools/validate.py   # expect: ALL OK
```

Play the stage alone: serve `stage/` with any static server (for example `python -m http.server -d stage -b 127.0.0.1 <port>`) and open `index.html#demo`. The stage loads fonts from the internet.

Keep files byte-exact: `.gitattributes` turns off all line-ending conversion, and the manifest check fails on a CRLF change.

## Known limits

The game state is held in memory only; a server restart loses the running game (planned, see `docs/HANDOFF.md` §12).
