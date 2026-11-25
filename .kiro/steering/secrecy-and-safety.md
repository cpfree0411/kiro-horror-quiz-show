---
inclusion: always
---

# Secrecy, cost and safety

## Game secrets
- Answers, explanations, OX picks, final picks, bet amounts, buzzer question text and music credits must not appear in any stage message, snapshot, caption, other player's phone view or log before their reveal event (`interface/KHQS_STAGE_INTERFACE.md` §5).
- Snapshots are a strict public projection. Phones get a private projection with only their own pick/bet.
- Asset ids are opaque (`a-` + hex). Asset files have no metadata and no telling file names. Credits go out only in `answer.revealed.credit`.
- `mc.caption` goes through the secret filter; no captions during a buzzer reading; never caption player speech.
- Test it: a secrecy scan over every emitted stream in the end-to-end tests.

## Live API, quota and keys
- The Gemini key is read from an environment file outside the repo when the MC connects. Never commit, print, log or send it to a browser. Never copy it into the repo or into another location.
- The owner uses the Gemini API free tier, so a real Live run needs no permission when a phase needs one. Free-tier quota and rate limits are still real: run it deliberately (smoke checks, the owner's play sessions), not in loops.
- Tests and CI never call the live API (deterministic, no quota use). Use the mock MC or a fake Live session.
- No automatic reconnect loops (they burn quota and hide failures). Keep the session caps (`docs/GAME_RULES.md` §11).
- If the show is reachable beyond localhost/LAN, starting a live MC session needs an operator secret or localhost; one live session at a time.

## Working rules
- Do not touch other services, ports or files on the host machine outside this repo. Pick unused ports and document them.
- Do not download new third-party media or fonts without the owner's OK; record license and source for every asset.
- Report honestly: what was verified (with the command/output or screenshot), what was not. A green build is not a played game.
- The README must disclose what was made before Kiro (stage, art, sound, protocol, prior prototype) and what was made with Kiro (`docs/HANDOFF.md` §10).
