# Kiro Horror Quiz Show

A kitschy, cute Halloween quiz show in the browser. A ghost MC hosts, one to three players answer with their phones, and the stage is a pre-made animated set. Built for the Kiroween hackathon.

**Status: phase P1 (engine core) done.** The game engine runs as a library with a simulated stage and MC in tests. The server, connector, phone UI and Gemini MC do not exist yet. What works today in a browser is the frozen stage played on its own (see below).

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

| Port | Bind | Serves |
| --- | --- | --- |
| `18830` | `127.0.0.1` only | The stage page, `/ws/stage`, the MC (start, reconnect), every operator action, and everything else. The owner reaches it through an SSH tunnel so the browser sees `localhost` (the microphone needs a secure context). |
| `18831` | the LAN address, default `192.168.50.216` (configurable by setting or environment variable), never `0.0.0.0` | Phone routes only: the ticket page, the phone controller page and its assets, the controller WebSocket, and the join API they use. |

Port `18831` does not serve `/ws/stage`, the stage page, MC start/reconnect or any operator action. This split is a P2 requirement and gets its own test.

Not used by this project and never to be bound: 8814, 18815, 18817, 18818. Nothing listens on 18830/18831 yet; the server arrives in P2.

## Layout

| Path | What |
| --- | --- |
| `stage/` | Frozen stage. Never edited. |
| `interface/` | Frozen protocol spec, schema, scenarios, validator. Never edited. |
| `media/` | Question music excerpts and credits. |
| `docs/` | `HANDOFF.md`, `GAME_RULES.md` (inputs) and later design notes. |
| `.kiro/steering/`, `.kiro/specs/` | Kiro steering and per-phase specs. |
| `server/khqs/` | The engine: `rules/` (pure), `content/`, `engine/` (state, flow, views). No I/O. |
| `tests/`, `scripts/` | Tests (`tests/support/` is the simulation harness) and dev helpers. |
| `MANIFEST.sha256` | Hashes of every file under `stage/` and `interface/`. |

## Develop

```bash
scripts/setup_dev.sh          # creates the venv outside the repo, installs dev dependencies
scripts/test.sh               # fast tests: manifest, validator, repo hygiene, engine (about 85 s)
scripts/test.sh -m slow       # the 5-minute static #demo run in headless Chromium
sha256sum -c MANIFEST.sha256  # the frozen boundary
python -B interface/tools/validate.py   # expect: ALL OK
```

Play the stage alone: serve `stage/` with any static server (for example `python -m http.server -d stage -b 127.0.0.1 <port>`) and open `index.html#demo`. The stage loads fonts from the internet.

Keep files byte-exact: `.gitattributes` turns off all line-ending conversion, and the manifest check fails on a CRLF change.

## License

Not chosen yet; the owner decides before submission. Plan: MIT for the code written in this repo. `stage/` and `media/` keep their own terms (`stage/CREDITS.md`, `media/CREDITS.md`) and are not relicensed.

## Known limits

The game state is held in memory only; a server restart loses the running game (planned, see `docs/HANDOFF.md` §12).
