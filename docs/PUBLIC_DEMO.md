# Public demo mode

A setting that makes the show safe to put behind a tunnel, so people can open a link and play. **Nothing in this repo deploys it or configures Cloudflare.** This page documents the intended setup and what the server guards.

## What a visitor gets
- The stage page, the phone ticket and controller, and the free **mock MC** (timed lines and captions, no voice). Never the live MC.
- One shared show: one game at a time. The first visitor to open the page becomes the main screen (primary); others watch. Phones join with the QR code or the link `https://<host>/ticket.html`.
- No operator buttons.

## Settings
| Variable | Meaning |
| --- | --- |
| `KHQS_PUBLIC=1` | turn public mode on |
| `KHQS_PUBLIC_HOST` | the tunnel's host name, bare (`demo.example.com`; no scheme, port or path). Required |
| `KHQS_OPERATOR_SECRET_FILE` or `KHQS_OPERATOR_SECRET` | the operator secret, at least 16 characters. Required. Prefer the file |
| `KHQS_MC=live` | optional: lets the **owner** start the live MC privately (below). Public visitors always get the mock |
| `KHQS_PUBLIC_PHONE_URL` | overrides the QR URL (default `https://<host>/ticket.html`) |
| `KHQS_PUBLIC_RESTART_STALE_S` | seconds without player input before a viewer can restart a running show (positive integer, default 60) |
| `KHQS_VISIT_LOG` | optional path for the owner-only JSONL visit log. Off by default and used only in public mode |
| `KHQS_VISIT_SALT_FILE` | path to a readable file containing at least 16 random bytes. Required when the public visit log is enabled |

Startup refuses public mode without a valid host or a secret, with a non-loopback stage listener, and `KHQS_MC=live` without a secret.

## Intended tunnel setup (documented only)
1. Create the secret once, readable only by you: `umask 077; mkdir -p ~/.config/khqs; head -c 24 /dev/urandom | base64 > ~/.config/khqs/operator.secret`.
2. Start the server: `KHQS_PUBLIC=1 KHQS_PUBLIC_HOST=demo.example.com KHQS_OPERATOR_SECRET_FILE=~/.config/khqs/operator.secret scripts/run.sh`. It still binds only `127.0.0.1:18830` (stage and everything the tunnel needs) and the LAN address `:18831` (phones in the room).
3. Point the tunnel at the **stage listener**: for a named Cloudflare tunnel, an ingress rule `hostname: demo.example.com` with `service: http://127.0.0.1:18830`. Keep the default Host header; **do not** rewrite it to `localhost`. WebSockets must be allowed (they are by default).
4. Optional extra layers at the edge (Cloudflare Access, WAF, rate limiting) are welcome but not assumed. The server enforces its own limits.
5. To stop: stop the tunnel, then the server. To rotate the secret: change the file and restart.

A quick tunnel gets a new random host name every run, so `KHQS_PUBLIC_HOST` would have to be set to it each time; a named tunnel with a fixed host is simpler.

## The guards (each has a test in `tests/server/test_public_mode.py` and `tests/test_guards.py`)
| Guard | Behaviour |
| --- | --- |
| Who is asking | A request is **local** only if the peer is loopback, the Host is `127.0.0.1`/`localhost`/`::1` and it carries no forwarding header (`X-Forwarded-For`, `CF-Connecting-IP`, `Forwarded`, …). It is **public** only if its Host is exactly `KHQS_PUBLIC_HOST`. Anything else: 403. Forwarding headers are believed only when the peer is the loopback tunnel |
| Operator actions | `POST /api/reset` with `force`, `/api/mc/*`, `/ws/mc`, `/api/diag` and `take=1` on `/ws/stage` are refused to public clients, and for local clients need the secret |
| The secret | Never in a page, URL, config, log or error. The operator types it at the moment of use (kept in page memory only; sent as a header, or as the first WebSocket frame). Compared in constant time. 5 wrong tries per minute locks that client for a minute. The log says only `operator secret rejected count=N` |
| Live MC | Starts only from a local request with the secret, only while no public client is connected and no game has players. While it runs the show is **private**: new public connections get 503 `PRIVATE SHOW IN PROGRESS`. Disconnecting it (or it stopping) returns to the public mock MC |
| One game | One engine, one primary stage. In public mode `start` and a normal NEW SHOW must come from the primary page (`X-KHQS-Cid`) |
| Public RESTART | `POST /api/restart` requires `X-KHQS: 1`, same-origin and an `X-KHQS-Cid` that uniquely identifies a connected public stage socket. The primary can restart as soon as someone has joined or the phase leaves the lobby. A viewer can restart from any lobby or after 60 seconds without player input. The chip asks for a second click within 3 seconds. The caller becomes the primary in a fresh lobby and the previous primary stays a viewer on reconnect. A private live-MC show returns 503 |
| GAME_RULES §11 caps | A public game is reset after 40 minutes, or after 240 s without player input (join, phone action, start, reset). Engine fail-safes cover stalls |
| Limits per client address | joins 2 per 5 minutes; connection attempts 30 per minute; start/reset/restart share 6 per minute; 8 concurrent sockets. Global: 12 stage sockets, 12 phone sockets. Limiter tables are bounded |
| Origin | Browser requests must be same-origin with the public host; cross-site `Origin` is refused |
| Headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: SAMEORIGIN` on public responses |
| Logs | The normal server log keeps phase and player-count diagnostics with access logging disabled. The optional owner-only visit log keeps event times, pseudonymous IDs, country codes, coarse device types and limited game milestones. It never stores raw IPs, full user agents, player names, answers, client IDs, credentials or secrets |

## Checking who used the demo

Keep the log and salt in separate files outside the repository and served directories. To enable the log, create a key once with `head -c 32 /dev/urandom > ~/.config/khqs/visits.key` under `umask 077`, then set `KHQS_VISIT_SALT_FILE` to that file and `KHQS_VISIT_LOG` to a private path such as `~/.local/state/khqs/visits.jsonl`. The server creates the log with mode `0600` and any new log parent with mode `0700`. It stops at 50 MB or on a storage error and emits one warning. If the disk falls behind, the bounded queue can drop events.

```sh
scripts/visits.py ~/.local/state/khqs/visits.jsonl
scripts/visits.py ~/.local/state/khqs/visits.jsonl --since 2026-11-28 --exclude-vid 0123456789ab --timeline
```

Dates and times in the report are KST. The daily and total rows count distinct non-bot IDs, with bot IDs and events shown separately. The country breakdown counts distinct non-bot IDs per country. Use `--exclude-vid` with one or more IDs to remove your own public visits. IDs come from a keyed hash of the address reported by the tunnel. A shared address can represent several people, an address or key change can give one person several IDs, and the device and bot categories are estimates. A timeline can show that a visitor ID was associated with a game that reached its ending. It cannot identify a judge or establish that someone watched every moment.

Page views and stage connections are recorded for public tunnel traffic with a forwarded address. The timeline attaches start, act and ending milestones to the public starter, or to the first public join if a local screen starts that game. Automatic resets use the same game attribution, with the first public join used for a lobby that never started. Accepted public RESTART and NEW SHOW requests are attributed to the caller. Direct local and LAN traffic is omitted.

## Known limits
- Visitors share one show. Only the main screen can start it. If someone leaves the main screen open in the lobby or abandons a running show, a viewer can use RESTART once it is stalled and become the main screen. A named tunnel plus Cloudflare Access would let you restrict who can open it.
- Per-address limits use the visitor address the tunnel reports (`CF-Connecting-IP`). Without a tunnel that sets it, everyone looks like one address.
- The pad panel and phone pages load Google Fonts from the internet, as the stage does.
- The owner deployed this setup on 2026-11-27 at `https://khqs.dterrarium.uk` (named Cloudflare tunnel, mock MC) and checked it from outside: pages 200, both WebSockets 101, a forced reset 403, and a phone joining and scoring in a real game. Still unverified: abuse beyond what the tests inject.
