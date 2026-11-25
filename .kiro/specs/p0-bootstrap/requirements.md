# P0 — Repo bootstrap: requirements

Source: `docs/HANDOFF.md` §11 (P0), §3 (frozen boundary), owner's start prompt.

## Goal
A new git repository containing the handoff package byte for byte, with the frozen boundary enforced by tests, a reproducible dev environment, and a private GitHub remote.

## Requirements (EARS)

| # | Requirement |
| --- | --- |
| R1 | The repository shall live at `/srv/workdata/projects/kiro-horror-quiz-show`, created only after `findmnt` shows an ext4 filesystem with UUID `59998928-c552-4d91-bc94-3d00054a8292`. Otherwise stop and report. |
| R2 | The repository root shall contain every file of the handoff package except `KIRO_START_PROMPT.md` and `PACKAGE.md`, byte for byte, including `.kiro/steering/`. |
| R3 | `sha256sum -c MANIFEST.sha256` shall pass in the repo root. |
| R4 | A test shall verify the manifest, and shall also fail on a file under `stage/` or `interface/` that is not in the manifest (which `sha256sum -c` cannot see). |
| R5 | `python interface/tools/validate.py` shall print `ALL OK`; a test shall assert it and shall assert that `check_engine_message` rejects a known-bad message. |
| R6 | `stage/index.html#demo`, served statically, shall run to `window.KHQS_showDone` with no page errors (a missing favicon is allowed). |
| R7 | Git shall be used from the first commit, with a **private** GitHub remote; only verified checkpoints are pushed. |
| R8 | `.gitignore` shall cover venvs, caches, runtime files and any `.env`. Git shall not convert line endings. |
| R9 | The venv, pip/uv cache and pytest cache shall be under `/srv/workdata`, set per tool and not through global environment overrides. |
| R10 | The Gemini key shall not be read, printed, copied or committed in this phase. A test shall scan the tree for key-shaped strings. |
| R11 | Two free ports shall be chosen (stage+MC on `127.0.0.1`, phones on the LAN interface), not 8814, 18815, 18817, 18818, and written in the README. |
| R12 | A `tech.md` steering file shall record the stack. |
| R13 | The README shall carry the handoff §10 disclosure from the start. |

## Out of scope
Any engine, server, connector or MC code (P1 onward). No edits to `stage/` or `interface/`.
