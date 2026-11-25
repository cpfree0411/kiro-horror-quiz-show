# P2 — design

## 1. Process
```
 python -m khqs.server  (one asyncio loop)
  ├─ GameHost            engine lifecycle, sockets, effect dispatch, recorder
  │    ├─ Engine         (P1, pure)
  │    ├─ MockMc         consumes Mc* effects, calls engine.mc_played / mc_caption
  │    └─ Pump           sleeps until engine.next_due(), woken by every input
  ├─ stage app   127.0.0.1:18830   all routes
  └─ phone app   <LAN host>:18831  phone routes only
```
Both apps are built from one route table: `PHONE_ROUTES` (ticket, phone UI, hook, join, `/ws/phone`) and `STAGE_ONLY_ROUTES` (stage page, static stage files, assets, connector, start, reset, `/ws/stage`). The phone app mounts the first list; the stage app mounts both. Routing is by explicit table, not by hiding paths, and a test walks both tables against both ports.

## 2. Modules (`server/khqs/`)
| Module | Role |
| --- | --- |
| `server/settings.py` | env → `Settings`; guards for hosts |
| `server/host.py` | `GameHost`: owns engine, sockets, `flush()` (drain effects → sockets/MC), `reset()`, pump |
| `server/app.py` | builds the two Starlette apps, handlers, origin guard, limits |
| `server/pages.py` | injection of the connector/ticket hook, static allowlist, media store |
| `server/record.py` | optional recorder (tests): stream, snapshots, views, MC effects, frames |
| `server/__main__.py` | runs both uvicorn servers; signal handling |
| `server/web/` | `link.js` (template), `ticket-hook.js`, `phone.html/css/js` |
| `mc/mock.py` | the mock MC |
| `content/dev_bank.py` | dev content (replaced in P4) |

## 3. Engine changes (small)
- `voice_input` flag (default = `mc_enabled`): the mock MC speaks but cannot hear; the holder gets a text box at once.
- `stats["gate_timeouts"]`, counted when a gate closes by its safety deadline (acceptance J1).
- Seat order 1 → 0 → 2 (owner answer 3).

## 4. Effect dispatch
`host.flush()` loops `engine.take_effects()` until empty: `StageBroadcast` → every stage socket; `StageDirect` → one; `PhoneChanged(seats)` → each seat's phone sockets get `{type:view}`; `Mc*` → `MockMc.handle`. Sends are queued per socket (`asyncio.Queue`, writer task) so a slow socket never blocks the loop; a socket whose queue overflows (200) is closed (the stage then reconnects and gets a snapshot).

`host.run(fn)` is the only way inputs reach the engine: call `fn()`, `flush()`, poke the pump. Everything is on the loop thread, so no locks.

## 5. Stage socket
Query: `cid` (client id, per tab), optional `take=1`. Flow: accept → wait for `stage.hello` (5 s) → if role `primary` and a primary exists: same `cid` or `take` → close the old socket (code 4001 `replaced`), `engine.stage_disconnect(old)`; then `engine.stage_hello(conn, role)`. Later frames → `engine.stage_message`. Close → `stage_disconnect`.

New game: a fresh `Engine` has no sockets; the host re-registers every open stage socket (previous primary first) so each gets the new lobby snapshot.

## 6. Phone socket
Hello with credential → `engine.seat_for_credential` → register socket under the seat; first socket → `phone_connection(seat, True)`; last close → `False`. Views are pushed from `PhoneChanged`. Actions → `engine.phone_action`; the result goes back with the client's `id`.

## 7. Connector
`/play/link.js` is rendered per request: the template plus a JSON config (`joinUrl`, `mc`: `mock`, `liveVoice: false`, `cid` is client-side). Steps:
1. Hash guard (F1) → return.
2. Capture the stage's `AudioContext` by wrapping `window.AudioContext` before `Sound.unlock()` creates it.
3. `LiveEngine` (F2) assigned to `window.MockEngine`.
4. Wrap `Sound.loop` and, for a live MC only, `Sound.cue`.
5. `KHQS_ENTRY`, `KHQS_JOIN_URL`, `KHQS_HOST` (created only when MC audio starts; P3).
6. DOM extras after `DOMContentLoaded`: operator chip, pad panel, `#hud{display:none}`.

`Sound` is a top-level `const`, so scripts reach it by name; its methods are plain properties and can be reassigned (verified by reading `sound.js`: `return { unlock, setEnabled, … }`).

## 8. Phone UI
Plain HTML/CSS/JS, one page, `data-screen` attribute per screen, `window.KHQS_PHONE` exposes `view`/`send` for tests. Select-then-LOCK IN is a small state machine per screen: tapping a choice sets `pending`; LOCK IN sends `{type, …}` once and disables the screen until the next view. A view change from the server clears `pending`. Countdown = `deadline - (serverTime + (now - receivedAt))`.

Pad: the stage page hosts `<iframe src="/phone?pad=<seat>">`; the credential is in `sessionStorage` (same origin, same tab), never in a URL.

## 9. Mock MC
Duration per cue: `clamp(60 ms × characters, 900, 6000)`, scaled by `KHQS_MOCK_SPEED` (tests use 0.5). Lines are English templates with `{name}`, `{number}` etc. from the cue's whitelisted facts. Captions go through `engine.mc_caption`, so the filter is exercised live; buzzer readings are blocked by it by design.

## 10. Test plan
Unit/integration (fast, real uvicorn on ephemeral ports, `websockets` sync client, `urllib`): port split, injection byte-identity, static allowlist, media route, origin guard, stage socket flow, reconnect race, phone socket flow and limits, join/start/reset API, pump with no stage, host config guards.
Browser (slow, Playwright + Chromium 1248): lobby join via pad and phone; games for 1/2/3 players; `#demo`; podium and NEW SHOW; phone UI screens with LOCK IN; frames captured for the secrecy scan.

## 11. Decisions
| Topic | Decision |
| --- | --- |
| Where the "credential" for the race lives | A per-tab `cid` in `sessionStorage`, sent as a query parameter on `/ws/stage`. The hello message is schema-frozen, so it cannot carry it. A duplicated tab copies `sessionStorage` in Chrome; "take over" and the chip make that visible. |
| Pad isolation | iframe, because stage CSS leaks into controllers (handoff trap 5). |
| Phone redirect | Ticket stays the frozen page; the hook moves the phone to `/phone` after the stamp. |
| Dev bank | Placeholder content so P2 is testable; P4 replaces it and adds board-fit checks. |
| Time scaling for tests | Only the mock MC speed; engine windows stay real. |
