# Kiro Horror Quiz Show

A kitschy, cute Halloween quiz show in the browser. A ghost MC hosts, one to three players answer with their phones, and the stage is a pre-made animated set. Built for the Kiroween hackathon.

**Status: phase P2 (server, connector, phones, mock MC) done.** The show runs end to end on the real stage with a free mock MC: lobby, opening, three acts, finale, NEW SHOW. Players use phones or the on-screen pad. The Gemini voice MC (P3), the real English question bank (P4) and submission polish (P5) are still to come. The questions in the server today are placeholder dev content.

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
scripts/run.sh            # stage on 127.0.0.1:18830, phones on 192.168.50.216:18831
```

Open `http://localhost:18830/` in the browser on the machine that shows the stage (the owner's Windows PC reaches it through the SSH tunnel). The lobby shows a QR code for the phone ticket at `http://192.168.50.216:18831/ticket.html`. Players without a phone type their name on the stage; their controller appears in a "SCREEN PAD" panel that everyone can see.

Settings (environment variables, all optional): `KHQS_STAGE_PORT`, `KHQS_PHONE_HOST` (default `192.168.50.216`; `0.0.0.0` is refused), `KHQS_PHONE_PORT`, `KHQS_PUBLIC_PHONE_URL` (the URL in the QR), `KHQS_SEED`, `KHQS_BUZZER_ANSWER_MS` (default 20000, the mock MC has no voice). Ports 8814, 18815, 18817 and 18818 are refused.

The bottom-left chip on the stage page shows PRIMARY or VIEWER, the MC mode and the phase. A second tab becomes a viewer; TAKE OVER makes it the primary. NEW SHOW (after the finale, or the chip with a confirmation mid-game) opens a new lobby; question sets alternate between games.

## Layout

| Path | What |
| --- | --- |
| `stage/` | Frozen stage. Never edited. |
| `interface/` | Frozen protocol spec, schema, scenarios, validator. Never edited. |
| `media/` | Question music excerpts and credits. |
| `docs/` | `HANDOFF.md`, `GAME_RULES.md` (inputs) and later design notes. |
| `.kiro/steering/`, `.kiro/specs/` | Kiro steering and per-phase specs. |
| `server/khqs/` | `rules/` (pure), `content/`, `engine/` (state, flow, views; no I/O), `mc/` (mock MC), `server/` (host, apps, connector and phone UI in `web/`). |
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

`scripts/test.sh` runs the fast suite (about two minutes). `scripts/test.sh -m slow tests/e2e/test_live_games.py -k players3` plays a full 3-player game in a real browser against the real server (about 4.5 minutes); run the three player counts, `test_live_misc.py` and `tests/e2e/test_stage_demo_static.py` in parallel processes to save time.

## Known limits

The game state is held in memory only; a server restart loses the running game (planned, see `docs/HANDOFF.md` §12).
