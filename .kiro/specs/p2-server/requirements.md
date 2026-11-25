# P2 — Server, connector, phones, mock MC: requirements

Sources: `docs/HANDOFF.md` §4–§8, §11 (P2), `interface/KHQS_STAGE_INTERFACE.md` §2, §7.1, §9.1, owner decisions after P1 (ports, lock-in, seats, reconnect race, podium proof).

## Goal
A running show: one process serves the frozen stage, the phone pages and the engine over two listeners, with a real clock pump, a connector that plugs the engine into the unmodified stage, a phone controller UI, an on-screen pad, and a free mock MC. A headless browser plays full games.

## Out of scope
Gemini Live and any real voice (P3). Real English questions and clips (P4; P2 uses a dev bank with the three real media files). Deploy and README polish (P5).

## Requirements

### A. Listeners and the port split
| # | Requirement |
| --- | --- |
| A1 | One process, one event loop, two listeners: the **stage app** on `127.0.0.1:18830` and the **phone app** on a configurable LAN address (default `192.168.50.216`) port `18831`. Ports and hosts come from settings/env. |
| A2 | Startup shall refuse a phone host of `0.0.0.0`, `::` or empty, and a non-loopback stage host. A loopback phone host is accepted only when `KHQS_ALLOW_LOOPBACK_PHONE=1` (tests). |
| A3 | The phone app shall serve **only**: `GET /ticket.html`, `GET /phone` and `/phone/*` assets, `GET /play/ticket-hook.js`, `POST /api/join`, and `WS /ws/phone`. Every other path (including `/`, `/index.html`, stage files, `/ws/stage`, `/api/start`, `/api/reset`, `/play/link.js`, `/stage/assets/*`) shall answer 404 / refuse the WebSocket. |
| A4 | The stage app shall serve everything: the phone routes plus the stage page, `/ws/stage`, assets, connector, `/api/start`, `/api/reset`. MC start/reconnect and every operator action exist only here. |
| A5 | Stage-only POSTs and `/ws/stage` shall reject a browser `Origin` that is not the stage app's own origin (`127.0.0.1` or `localhost` on the stage port). Operator POSTs shall also require the header `X-KHQS: 1`. |
| A6 | No access log shall be written (credentials travel in WebSocket messages, not URLs); server logs carry phase and player count only. |

### B. Pages, assets, injection
| # | Requirement |
| --- | --- |
| B1 | Every file under `stage/` that is served shall be byte-identical to disk, except `index.html` (exactly one `<script src="/play/link.js"></script>` inserted right after `mock-engine.js`'s tag) and `ticket.html` (one hook script tag before `</head>`). `stage/tools/` and docs files are not served. Serving shall fail loudly if an anchor is missing or appears twice. |
| B2 | `GET /stage/assets/{id}` shall serve a media file only for a known opaque id (`a-` + hex), with `audio/mpeg`, no `Content-Disposition`, no title in any URL or header, cacheable. Unknown ids → 404. |
| B3 | The served stage shall still pass `MANIFEST.sha256` on disk (the server never writes to `stage/`). |

### C. Stage socket and the clock pump
| # | Requirement |
| --- | --- |
| C1 | `/ws/stage` shall take `stage.hello` first, answer with a snapshot, then deliver every stream message in order to every stage socket. Direct replies (pong, error, snapshot) go only to the asking socket. |
| C2 | A pump shall sleep until `engine.next_due()` (woken early by any input) and call `poll()`; it shall keep running with no stage connected. |
| C3 | First `primary` hello wins; later ones become `viewer` with `error primary_taken`. A hello that carries the same client id (`cid` query parameter, kept per tab in `sessionStorage`) as the current primary shall **close the old socket first** and become primary (reconnect race). An explicit operator "take over" (`take=1`) shall replace any primary. A different tab without `take` stays a viewer. |
| C4 | Closing every stage socket shall not stop the game. |

### D. Phone / controller socket
| # | Requirement |
| --- | --- |
| D1 | `/ws/phone`: the first message is `{type: hello, cred}`; a bad credential gets `{type: error, code: bad_cred}` and a close. A good one gets the player's private view; every change pushes a fresh view; actions return `{type: result, id, ok, error}`. |
| D2 | A seat counts as connected while at least one of its sockets is open (`seat.connection` on first open and last close). Reload or reconnect keeps the seat and score. |
| D3 | Limits: messages ≤ 2 KB, ≤ 20 messages/s per socket, ≤ 4 sockets per seat; violations close the socket. |

### E. HTTP API
| # | Requirement |
| --- | --- |
| E1 | `POST /api/join {name}` (both ports) → `{ok, seat, credential}` or `{error}` using the engine's English error strings. The credential appears only in this response. |
| E2 | `POST /api/start` (stage only) starts the show; errors are short English strings. |
| E3 | `POST /api/reset {force}` (stage only): without `force` only when the game has ended; with `force` any time (operator). A new game uses the next game index (question sets alternate), a new seed, a fresh engine; stage sockets keep their roles and receive the new lobby snapshot; phone sockets of the old game receive `gone` and close. |

### F. Connector (`/play/link.js`)
| # | Requirement |
| --- | --- |
| F1 | It shall do nothing when the URL hash contains a replay/demo token: `act=`, `step=`, `opening`, `showtime`, `clean`, `verdict=`, `demo`, `finale=`, `trans=`. |
| F2 | It replaces `window.MockEngine` with a same-shaped WebSocket engine (`receive`, `load`, `start`, `stop`, `labels`, `speed`, `paused`, `run`, `scenario`, `send`, `sleep`): queue until open; drop `pong`; handle `error`; drop stream messages with `sseq <= last`; reconnect after 1 s with `stage.hello {lastSseq}`; ping every 10 s; viewers never forward `beat_done` or `media_*`. |
| F3 | On `buzzer.pressed` it calls `KHQS_HOST.stopMc()` if the host exists; on `act.started` it prefetches the listed assets. |
| F4 | It wraps `Sound.loop('waltz')` so `on` plays `[startSec, endSec]` of the real asset on the shared `AudioContext` (captured from the stage's own), and `off` stops it; other loops pass through. When `KHQS_HOST` exists it calls `setMicGate('media', …)`. |
| F5 | It keeps the placeholder `voice` cue for the mock MC and drops it only when the config says a live MC speaks. |
| F6 | It defines `KHQS_ENTRY {join, start, reset}` and `KHQS_JOIN_URL`; a failed `start` writes an English message into the lobby error element and re-enables the start sign. |
| F7 | It adds an operator chip (role, connection, MC mode, phase, NEW SHOW, TAKE OVER), hides the stage HUD, and adds the **screen pad**: an iframe panel per pad player with the label that the pad is visible to everyone. |
| F8 | The ticket hook defines `KHQS_TICKET_JOIN` before the page script, stores the credential, and sends the phone to `/phone` after the ADMITTED stamp. |

### G. Phone UI
| # | Requirement |
| --- | --- |
| G1 | English only; big touch targets; works on a phone browser; scoped styles; fonts only from the same Google Fonts the stage uses; dark wood, warm bulbs, cream paper. |
| G2 | Screens: waiting, OX, buzzer, betrayal reason, betrayal decision, answer (voice wait + "type instead", text box), bet, final choice, locked/waiting variants, done. |
| G3 | **Select, then LOCK IN.** OX, final choice, betrayal reason and decision, and the bet are chosen first and sent only when LOCK IN is pressed. BUZZ and the typed answer send at once. |
| G4 | It shows only the player's own pick and bet, a countdown computed from server time, a reconnect banner, and a clear "scan the QR again" screen for a bad credential. |

### H. Mock MC
| # | Requirement |
| --- | --- |
| H1 | It consumes the engine's MC effects with the same playback-cursor contract: each `McSay` is "played" after a simulated duration, then `mc_played(token)`; an interrupt cancels pending lines. |
| H2 | It has no voice input: the engine is built with `voice_input=False`, so a buzz holder gets the phone text box at once. |
| H3 | It sends short English progress lines as captions through the engine's secret filter. |

### I. Content
| # | Requirement |
| --- | --- |
| I1 | A dev bank (two sets, three tracks mapped to the real `media/` files by opaque ids, credits from the handoff table) lets the server run until P4. It is validated with `validate_bank`. |

### J. Acceptance (headless Chromium, mock MC, real stage)
| # | Requirement |
| --- | --- |
| J1 | Full games complete for 1, 2 and 3 players; one player uses the screen pad; one phone reloads mid-game; the stage is `primary`; no gate closed by safety timeout; page errors 0; every gate acked. |
| J2 | A secrecy scan over the engine stream, its snapshots, phone views, MC commands **and the frames the browsers actually received** is clean. |
| J3 | `#demo` on the live server plays as a mock to `KHQS_showDone`. |
| J4 | At the end the podium is drawn and NEW SHOW appears only after `game.ended`; NEW SHOW opens a new lobby. |
| J5 | Port-split, injection byte-identity, origin guard, reconnect-race and phone-socket limit tests pass. |
