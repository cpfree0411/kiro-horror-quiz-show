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
| GAME_RULES §11 caps | A public game is reset after 40 minutes, or after 240 s without player input (join, phone action, start, reset). Engine fail-safes cover stalls |
| Limits per client address | joins 2 per 5 minutes; connection attempts 30 per minute; start/reset 6 per minute; 8 concurrent sockets. Global: 12 stage sockets, 12 phone sockets. Limiter tables are bounded |
| Origin | Browser requests must be same-origin with the public host; cross-site `Origin` is refused |
| Headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: SAMEORIGIN` on public responses |
| Logs | phase and player count only; no names, answers, secrets, access log |

## Known limits
- Visitors share one show; a stranger who opens the page first is the main screen. Only they can start and restart it. A named tunnel plus Cloudflare Access would let you restrict who can open it.
- Per-address limits use the visitor address the tunnel reports (`CF-Connecting-IP`). Without a tunnel that sets it, everyone looks like one address.
- The pad panel and phone pages load Google Fonts from the internet, as the stage does.
- The owner deployed this setup on 2026-11-27 at `https://khqs.dterrarium.uk` (named Cloudflare tunnel, mock MC) and checked it from outside: pages 200, both WebSockets 101, a forced reset 403, and a phone joining and scoring in a real game. Still unverified: abuse beyond what the tests inject.
