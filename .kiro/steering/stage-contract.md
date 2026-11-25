---
inclusion: always
---

# Stage contract (frozen)

- **Never edit anything under `stage/` or `interface/`.** No refactors, formatting, renames, "small fixes" or new files there. `MANIFEST.sha256` must keep passing.
- The engine talks to the stage only through `khqs.stage/1` over `/ws/stage`. The JSON Schema `interface/stage-protocol.schema.json` is the truth; it forbids extra fields. Validate every outgoing message in tests with `interface/tools/validate.py`.
- The server serves stage files unchanged except for **one injected script tag** after `mock-engine.js` in `index.html` (the connector) and one hook script in `ticket.html`'s `<head>`.
- The connector replaces `window.MockEngine` with a same-shaped WebSocket engine, wraps `Sound.loop('waltz')` to play the real question music, drops the placeholder `voice` cue when the live MC speaks, defines `KHQS_ENTRY` / `KHQS_JOIN_URL` / `KHQS_HOST`. Details: `docs/HANDOFF.md` §5.
- The connector must stay out of the way for replay/demo hashes: `act=`, `step=`, `opening`, `showtime`, `clean`, `verdict=`, `demo`, `finale=`, `trans=`.
- `sseq` is per game, contiguous from 1, never consumed by snapshots. Exactly one gate open at a time. A gate closes on the primary stage's `beat_done` (matching id **and** sseq) plus the MC reaction finishing playback, or on the safety timeout (`timeoutMs` + 25 s).
- Do not reinterpret the opening, lobby, transitions, animation, finale or sound timing. If the stage truly cannot express something, write it in `docs/STAGE_REQUESTS.md` and stop; the visual owner changes the stage.
- Only four fan puppets have art: `vampire`, `sack`, `bolt`, `tophat_skull`. Assign different ones.
