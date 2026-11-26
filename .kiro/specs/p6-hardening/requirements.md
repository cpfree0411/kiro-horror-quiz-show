# P6 — Public demo mode, soak, hooks, Kiro usage: requirements

Owner instructions after P4 (another agent wrote `banks/en-bank.json` and `tests/test_en_bank.py`; both are off limits, and so is question content). Rules as before: spec first, stop and report, never print/log/copy the Gemini key, no API calls in tests, do not touch other services or ports, do not deploy and do not touch Cloudflare.

## 1. Public demo mode (`KHQS_PUBLIC=1`)
Goal: the show can be exposed through a tunnel (documented only, not set up) without strangers reaching operator powers, the live MC or the API quota.

| # | Requirement |
| --- | --- |
| P1 | Public mode needs `KHQS_PUBLIC_HOST` (the tunnel's host name). Startup refuses public mode without it, with a host that has a scheme, port, path or space, and with a stage listener that is not loopback. |
| P2 | A request is classified as **local** (peer is loopback, Host is `127.0.0.1`/`localhost`/`::1`, and no forwarding header such as `X-Forwarded-For`, `CF-Connecting-IP`, `Forwarded`, `X-Real-IP`) or **public** (Host equals the public host). Anything else gets 403. Without public mode only local is accepted, as before. |
| P3 | Public mode serves the stage page, the phone routes and `/ws/stage`, `/ws/phone`, `/api/join` to public clients with the **mock MC only**: the page config says `mock`, and `/api/mc/*` and `/ws/mc` are refused to public clients. |
| P4 | The live MC can start only from a **local** request that carries the operator secret. The secret comes from `KHQS_OPERATOR_SECRET` or `KHQS_OPERATOR_SECRET_FILE` (at least 16 characters), is compared in constant time, never appears in a log, a page, a config or an error, and is typed by the operator at the moment of use (kept in page memory only). Public mode with `KHQS_MC=live` is refused without a secret. |
| P5 | Failed secret attempts are limited (5 per minute per client, then 429 for a minute) and logged as a count only. |
| P6 | Operator actions are refused to public clients and need the secret in public mode: `POST /api/reset` with `force`, `POST /api/mc/connect`, `POST /api/mc/disconnect`, `GET /api/mc/status`, `/ws/mc`, and `take=1` on `/ws/stage`. |
| P7 | While the live MC is connected in public mode the show is **private**: new public connections are refused (503 `PRIVATE SHOW IN PROGRESS`), and connecting the live MC is refused while any public client is connected or a game is running. |
| P8 | One game at a time (one engine; one primary stage). In public mode `POST /api/start` and a normal `POST /api/reset` from a public client must carry the primary stage's client id (`X-KHQS-Cid`). |
| P9 | The caps of `docs/GAME_RULES.md` §11 apply to a public game: 40 minutes per game, 240 s without player input (join, phone action, start, reset) resets an unfinished game to a fresh lobby; stalls are covered by the engine's own fail-safes. |
| P10 | Limits per client IP (taken from `CF-Connecting-IP`/`X-Forwarded-For` only when the peer is loopback, i.e. the tunnel): joins 2 per 5 minutes, connection attempts 30 per minute, start/reset 6 per minute, 8 concurrent sockets. Global caps: 12 stage sockets, 12 phone sockets. Limiter state is bounded. |
| P11 | Public responses carry `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: SAMEORIGIN`. Public mode forces the join URL (QR) to `https://<public host>/ticket.html`. |
| P12 | Every guard above has a test. The tunnel setup is documented (`docs/PUBLIC_DEMO.md`); nothing is deployed. |

## 2. Soak and robustness
| # | Requirement |
| --- | --- |
| S1 | 30 back-to-back mock games through NEW SHOW against a real server with real sockets (stage client and phone clients), short windows. |
| S2 | Phone reload/reconnect storms and stage reconnect storms (same client id and take-over). |
| S3 | A 60-minute idle server. |
| S4 | Report memory (RSS), open sockets/descriptors, threads, asyncio tasks, pending timers and the sizes of the host's tables, before and after, and at intervals. Fix any growth found. A fast regression test covers the leak classes fixed. |

## 3. Kiro hooks
| # | Requirement |
| --- | --- |
| H1 | Hooks in `.kiro/hooks/` run `sha256sum -c MANIFEST.sha256` (plus the extra-file check) when `stage/`, `interface/` or the manifest change; run `scripts/check_bank.sh` on the banks when banks, media or content code change; run a quick test subset when rules, content or prompt code changes; and run the same checks when the agent ends a turn. Each finishes in seconds. |
| H2 | The full fast suite (about two minutes) is not a hook; it is documented as an on-demand command. |
| H3 | A test checks the hook files (format, matchers hit real files, commands exist) and the scripts they call. |

## 4. `docs/KIRO_USAGE.md`
A factual account, phase by phase, of how Kiro was used: specs, steering, hooks, the validation sub-agent, what was verified and how, with citations to files under `.kiro/`. It states plainly what was made outside Kiro (stage, art, sound, question content) and claims nothing that was not done.

## Not in scope
Deploying, DNS, Cloudflare configuration, changing `banks/en-bank.json` or `tests/test_en_bank.py`, changing question content.
