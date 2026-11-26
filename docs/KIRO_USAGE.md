# How Kiro was used in this repo

This is a factual account for the Kiroween submission. It lists what Kiro did, what it did not do, and how each result was checked. Every claim points at a file in the repo.

## What was made outside Kiro

Kiro did not make any of these. They came in the handoff package or were added by someone else:

- **The stage**: `stage/` (page, scripts, styles), its art plates, animation, transitions, opening, lobby and finale. Made by the project owner with other AI tools: Claude Code for the stage code, ChatGPT image editing for the art plates, Gemini for some music, Pixabay for the sound effects (`docs/HANDOFF.md` section 1).
- **Sound effects and music cues** under `stage/`.
- **The wire protocol** `khqs.stage/1`: `interface/` (spec, JSON Schema, scenarios, validator).
- **The question content.** The English bank `banks/en-bank.json` and `tests/test_en_bank.py` (commit `c9aaa01`, phase P4) were written by another agent, after Kiro's P3, with Claude Code. Kiro was told not to edit them in P6 and did not. In P7 the owner told Kiro to add exactly three `composer` values to `banks/en-bank.json`; that is the only change Kiro made to the file (three added lines, `git diff c9aaa01 -- banks/en-bank.json`), and the question content is untouched.
- **Five of the six steering files**: `product.md`, `stage-contract.md`, `language-and-voice.md`, `secrecy-and-safety.md`, `structure.md` came in the handoff. Kiro edited `product.md` and `language-and-voice.md` in P3 for the English-only scope change.

`MANIFEST.sha256` pins every frozen file. Kiro copied those files in P0 and has not edited them since; this is checked by `scripts/check_manifest.sh` (see "Hooks").

## What Kiro made

Everything under `server/`, `tests/`, `scripts/`, `docs/` other than `HANDOFF.md`, the specs in `.kiro/specs/`, `.kiro/steering/tech.md` and the hooks in `.kiro/hooks/`. Commits by phase:

| Phase | Commit | Content |
| --- | --- | --- |
| P0 | `d6222e8`, `ea2b576` | Repo bootstrap from the handoff, manifest check, stack choice, ports |
| P1 | `c9666d6` | Engine core: rules, content model, flow, views, simulation harness |
| P2 | `c22e9b2` | Server, connector, phone UI, mock MC, port split, headless-browser acceptance |
| P3 | `f2e323a` | Gemini Live MC, browser audio host, bank format and loader, English-only scope, collapsible pad |
| P4 | `c9aaa01` | Not Kiro's: English question bank and its tests |
| P6 | `a11d210` | Public demo mode, soak and leak fixes, hooks, docs |
| P7 | `a250331` | Spoken hints on request in the music question (consent, `composer` in the bank format), worst-case timing script |
| P7 fix | `1f0d0b2` | Hold a cue until the model's tool-call turn ends; a fake transport that models it (found in the owner's play test) |

P5 (packaging the submission: README pass, `LICENSE`) was done by Claude Code, not Kiro. The play-test facts marked *(P5)* in this file were added then.

## Steering

Steering files are in `.kiro/steering/`, all with `inclusion: always`.

- From the handoff: `product.md`, `stage-contract.md`, `language-and-voice.md`, `secrecy-and-safety.md`, `structure.md`. They set the frozen boundary, the secrecy rules (nothing about an answer reaches the model before its reveal), the key rule (the Gemini key is read only at MC connect, never printed or committed), and the repo layout.
- Written by Kiro in P0: `tech.md`, the stack and environment notes (venv outside the repo, `-B` so no `__pycache__` appears under `interface/`). Edited in P2, P3 and P6 as the stack grew.

Rules from steering that changed what Kiro did: the frozen-file boundary became a manifest test in P0 and a hook in P6; the secrecy rule became a full-game scan of every prompt, tool result and caption in P3 (`tests/server/test_live_mc.py`); the key rule became tests with sentinel values.

## Specs

Each phase started with a spec before code: requirements, design, tasks. At the end of each phase a `verification.md` maps every requirement to the test or run that shows it.

| Phase | Spec folder | Files |
| --- | --- | --- |
| P0 | `.kiro/specs/p0-bootstrap/` | requirements, design, tasks (no verification file) |
| P1 | `.kiro/specs/p1-engine-core/` | requirements, design, tasks, verification |
| P2 | `.kiro/specs/p2-server/` | requirements, design, tasks, verification |
| P3 | `.kiro/specs/p3-live-mc/` | requirements, design, tasks, verification |
| P4 | none | the other agent wrote no spec |
| P6 | `.kiro/specs/p6-hardening/` | requirements, design, tasks, verification |
| P7 | `.kiro/specs/p7-music-hints/` | requirements, design, tasks, verification |

The owner reviewed and accepted each phase (P0 to P3) before the next began. Several of the owner's answers shaped the specs: competition ranking, first submission final with a select-then-LOCK IN phone UI, join order seats 1, 0, 2, the interface table as the truth for gate timeouts, and the English-only scope.

## How things were verified, by phase

Fast test counts at the end of each phase (`scripts/test.sh`, pytest). Slow tests run real headless Chromium and take minutes each.

| Phase | Fast tests | Slow tests | Notes |
| --- | --- | --- | --- |
| P0 | 8 | 1 (static `#demo` page, 280 s) | Manifest, validator, extra-file check |
| P1 | 179 | 0 | Rules and engine against the interface validator and scripted full games |
| P2 | 239 | 8 | Real sockets, phone and stage pages in Chromium, port split |
| P3 | 319 | 10 | Fake Live transport in tests; browser audio host test |
| P6 | 392 | 11 | Includes `tests/e2e/test_public_browser.py` |
| P7 | 542 | 12 | Includes `tests/e2e/test_music_hint_browser.py` (HINT button and AGREE / NO on real phone pages, mock MC) |

Where verification found real problems:

- P0: `scripts/setup_dev.sh` was broken. Found in P1 when it was used for the first time.
- P2: the on-screen pad covered the NEW SHOW button. Found in a screenshot from the browser acceptance run. Fixed with a collapsible pad.
- P3: the first real Gemini run showed a bug that the fake transport had hidden. A buzz that cut a reading in flight left the microphone closed (drain and listen logic). Fixed, with a test that fails without the fix (`tests/server/test_live_mc.py`).
- P6: the soak run found three leaks, listed below.
- P7: the browser test for the HINT button failed four times before it passed, each time because of the test and not the engine: an assertion that looked at the last two judged answers of the whole game instead of the music question, a plan that assumed one fixed music track although the seed and the number of joins pick it (found by dumping every phone action to a file), and an assertion on a screen that lasts less than one poll. A driver race (a stale phone view letting the answer branch fire right after the HINT tap) was fixed on suspicion while debugging and is not shown to have mattered. The unit run found one engine bug: a bare "don't" was a refusal phrase, which made "I don't know" a NO (`rules/hints.py`, tests in `tests/test_hint_rules.py`), and two smaller view and test mistakes.

### Validation sub-agent

The `validation` sub-agent was used once, at the end of P2, with the verdict PASS. It noted that "credential" in the join rule is read as the per-tab client id. It was not used in P3, P6 or P7.

### Web search

Web search was used once, in P3, to check the current Gemini Live model name. The chosen default (`gemini-3.8-live`, configurable) is in `.kiro/specs/p3-live-mc/design.md`.

### Real Gemini sessions

Four real Live sessions, all in P3 (one speech fixture, three smoke games), logged outside the repo in `/srv/workdata/build-cache/khqs-evidence/p3/`. Tests never call the live API. P6 and P7 opened no real session; the P7 fix opened one (`scripts/live_smoke.py hint`, see below). *(P5)* The owner's own play tests on 2026-11-27 ran five more sessions with a human voice.

## P6 in detail

### Public demo mode

Spec: `.kiro/specs/p6-hardening/requirements.md` (P1 to P12). Code: `server/khqs/server/guards.py`, `app.py`, `host.py`, `settings.py`. Guide: `docs/PUBLIC_DEMO.md`. Tests: `tests/test_guards.py` (13), `tests/server/test_public_mode.py` (18), `tests/e2e/test_public_browser.py` (1, slow). A tunnel was **not** set up and Cloudflare was not touched; the document describes the intended setup only.

### Soak and robustness

`scripts/soak.py` runs the server as a separate process and reads numbers from `/proc/<pid>` and from `/api/diag` (enabled only with `KHQS_DIAG=1`). In-process measurement was tried first and was polluted by the client threads. Findings and fixes:

1. Join-grace timers were never cancelled, so each game left two timers and kept an engine alive (timers 4 to 63 over 30 games, RSS +5 MB). Fixed in `host.py`.
2. A connection whose writer queue was full did not cancel its writer task on close. Fixed in `Conn.close()`.
3. A phone reload made the seat flap offline and online, and each flap sent messages to the stage (about 1000 stream messages per storm round). The phone disconnect is now debounced (`disconnect_grace_s`, default 2 s). Stream growth fell to 2 per round.

Four tests in `tests/server/test_leaks.py` cover them; three were run against the unfixed code and failed there. Numbers are in `.kiro/specs/p6-hardening/verification.md`.

### Hooks

Files: `.kiro/hooks/frozen-boundary.json`, `bank-check.json`, `quick-tests.json`, `stop-gate.json`. They call `scripts/check_manifest.sh` (`sha256sum -c MANIFEST.sha256` plus a check for extra files), `scripts/check_banks.sh` (`scripts/check_bank.sh` on every bank), `scripts/test_quick.sh` (about 10 s) and `scripts/check_all_quick.sh` (all three, run when the agent ends a turn).

- The full fast suite takes about 3.5 minutes, so it is not a hook. Run `scripts/test.sh` on demand.
- The hooks were created with Kiro's `createHook` tool. The tool wrote them to the workspace root (`/srv/workdata/projects/.kiro/hooks/`), so they were moved into this repo's `.kiro/hooks/`.
- `tests/test_kiro_hooks.py` (18 tests) checks the hook files: format, that each matcher hits real paths and misses others, that the commands exist and run, and that a changed file in a temporary copy of `stage/` makes the manifest script fail. It works on temp copies, so the real `stage/` is never touched.
- **Firing check, first attempt: no hook was seen to fire.** After P6 was accepted, a one-character edit to `tests/test_guards.py` (a file the `quick-tests` hook matches) was saved through the agent's file-edit tool in the same session that had created the hooks. No hook output came back and no `test_quick.sh` process ran. The edit was reverted (`git status` clean). A second attempt in P7, a docstring edit to `server/khqs/rules/hints.py` (also matched by `quick-tests`) through the file-edit tool, gave the same result in the same session. Kiro loads hooks at session start, so this session, which began before the hooks existed, is the expected case for "not loaded", and the result says nothing about a fresh session.
- **Still not verified:** that a hook fires in a session that started after the hook files were committed. The format, the matchers and the scripts are verified, by hand and by `tests/test_kiro_hooks.py`. The check is to be repeated in the next session and this paragraph updated with the result.

## P7 in detail

Spec first: `.kiro/specs/p7-music-hints/requirements.md` (taken from the owner's prompt, with numbered requirements), `design.md`, `tasks.md`, then `verification.md` with a requirement to test table and the worst-case timing numbers. The new code is `server/khqs/rules/hints.py` (phrase lists), the engine flow (`hint_turn` in `server/khqs/engine/flow.py`), five MC cues and the `report_vote` tool, the phone buttons, and a required `composer` in `khqs.bank/1`. The stage was not touched; the frozen stage shows only `phase.changed buzzer.hint` ("HINT!") and the MC captions for a request, and the notes on what a visible cue would need are in the P7 report.

Verified with the fake Live transport and scripted players (the real model has so far only been used by the owner's own play test): unit tests for each rule, `assert_no_leaks` over 16 full games that use hints (the scanner was extended and has a test that it catches an early clue), and one slow browser game with the HINT button. `scripts/music_timing.py` measures the worst-case length on a fake clock.

### P7 fix after the owner's play test

The owner's live-voice test found that the MC never spoke the hint. All P7 tests had passed because the fake Live transport answered a turn at once and never modelled the open turn around a tool call. The fix made the fake behave like the real API, added a regression test that fails on `9b10881`, and changed `server/khqs/mc/live.py` (details in `.kiro/specs/p7-music-hints/verification.md`). A scripted check against the real API (`scripts/live_smoke.py hint`) used its one session and stopped on a mistake in the script itself; it has not been repeated.

## Limits of this account

- The stage, art, sound and question content were made outside Kiro.
- No real Cloudflare tunnel was set up. Public mode was tested against local requests with forwarding headers and a fake public host.
- *(P5)* Human voice: the owner played live-voice games in one room on 2026-11-27, solo and with two phones. Kiro's own real sessions used a synthetic voice through a fake microphone.
- The hooks have not been seen firing inside Kiro (two attempts, both in the session that created them, no firing; not yet repeated in a fresh session).
- *(P5)* The spoken hint request and the spoken yes or no worked with the real Live model in the owner's play tests on `1f0d0b2`: the hint line had audio (7.3 s solo, 7.1 s in the two-phone game) and a spoken vote arrived as `report_vote`. Several people talking at once in the vote has not been tried.
