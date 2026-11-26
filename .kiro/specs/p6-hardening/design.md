# P6 — design

## 1. Public mode

```
 internet ─► tunnel (cloudflared, on this host) ─► 127.0.0.1:18830 (stage app)
                                                      │ classify(request) → local | public | refuse
 owner (SSH tunnel / localhost) ───────────────────────┘
 LAN phones ─► 192.168.50.216:18831 (phone app, unchanged)
```
`guards.py` (new, pure, injectable clock): `classify(headers, peer, settings)`, `client_ip(headers, peer)`, `RateLimiter` (token buckets, pruned), `OperatorAuth` (constant-time compare, per-client lockout). `app.py` calls them at the top of every handler through one `gate()` helper, so a route cannot forget.

| Route | public client | local client (public mode) | local client (normal mode) |
| --- | --- | --- | --- |
| `/`, static, `/play/link.js`, media, `/ticket.html`, `/phone` | yes (config `mock`, `operator:false`) | yes (`operator:true`) | yes |
| `/ws/stage`, `/ws/phone`, `/api/join` | yes, limited | yes | yes |
| `/api/start`, `/api/reset` (normal) | only with the primary's `X-KHQS-Cid`, limited | yes | yes |
| `/api/reset {force}`, `take=1` | no | needs secret | yes |
| `/api/mc/*`, `/ws/mc` | no | needs secret | yes |

Live MC in public mode: `connect` is refused unless the request is local with a valid secret, no public client is connected, and no game is running. A successful connect sets `host.private_show`; new public connections get 503 until the MC disconnects, stops, or the show is reset. This avoids the trap where public browsers would wait for audio they never get.

`/ws/mc` cannot send headers from a browser, so in public mode its first message `{t: hello, secret}` carries the secret (never in the URL).

## 2. Caps (§11) for public games
A watchdog task in `GameHost` (public mode only): game age ≥ 40 min → forced reset; players present and no player input for 240 s → forced reset to a fresh lobby (`host.last_input` is bumped by join, phone actions, start, reset). Both log a line with the phase and player count only.

## 3. Leak hunting
Instrument: `process_stats()` returns RSS (from `/proc/self/status`), open descriptors and sockets (`/proc/self/fd`), threads, asyncio tasks, scheduled loop handles, and the host tables (`stage`, `phones`, `mc._pending`, rate-limiter sizes, engine stream length). `scripts/soak.py` drives a real server with real sockets (no browser): a stage client that acks gates and answers media events, phone clients that play, fast windows, and the mock MC speed-up. Modes: `games N`, `storm`, `idle SECONDS`. Each prints a table and appends JSON lines to a report file.

Suspect from reading the code: `Conn.close()` swallows `QueueFull` without stopping the writer task, so a socket closed with a full queue leaves a task behind. Fix: cancel the writer on close.

## 4. Hooks
`scripts/check_manifest.sh` (sha256sum -c plus extra-file check), `scripts/check_banks.sh` (all `banks/*.json`), `scripts/test_quick.sh` (rules, content, banks, prompts, hooks; a few seconds). `.kiro/hooks/*.json` call them on `PostFileSave`/`PostFileCreate`/`PostFileDelete` with path matchers, and a `Stop` hook runs all three and returns exit 1 with the reason on failure so the agent keeps working.

## 5. Docs
`docs/PUBLIC_DEMO.md` (tunnel recipe, settings, what is guarded), `docs/KIRO_USAGE.md` (facts, with file citations), README updates.

## Decisions
| Topic | Decision |
| --- | --- |
| Why the live MC and public clients exclude each other | A public browser has no audio socket; playback reports would never arrive and the MC would stall and stop. |
| Public stage | Anyone can open the stage; the first becomes primary, the others watch. Only the primary's client id may start or reset. |
| Proxy headers | Trusted only when the peer is loopback (the tunnel). A request with forwarding headers can never be "local". |
| Host rewriting | The tunnel must not rewrite Host to `localhost`; the operator secret is the real guard either way. |
