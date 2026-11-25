---
inclusion: always
---

# Tech stack

Chosen in P0 (see `.kiro/specs/p0-bootstrap/design.md`). The handoff leaves the stack open; this is the proven reference stack.

- **Language / runtime:** Python 3.12 (`requires-python >= 3.12`), asyncio, one process, one worker, memory-only state.
- **Server (P2):** an ASGI app (Starlette) on uvicorn, WebSocket for `/ws/stage` and the controller channel. Added in P2 with its first use.
- **MC (P3):** `google-genai` for Gemini Live, behind a small adapter interface. A mock MC with the same playback-cursor contract is the default for tests and development.
- **Tests:** pytest. Browser end-to-end tests use Playwright for Python, pinned to 1.64.1 to match the Chromium builds cached in `/srv/workdata/browser-cache/ms-playwright`.
- **Layout:** `server/` holds the engine (pure, no I/O, injectable clock and RNG) and the thin adapters. `tests/` holds unit, protocol and end-to-end tests. `scripts/` holds dev helpers.
- **Dev environment on the owner's host:** the venv lives outside the repo at `/srv/workdata/projects/.venvs/kiro-horror-quiz-show`. Cache locations are passed per tool (`uv --cache-dir`, `pytest -o cache_dir`, `PLAYWRIGHT_BROWSERS_PATH` inside `scripts/test.sh`), never set as global environment overrides. Use `scripts/setup_dev.sh` and `scripts/test.sh`.
- **Frozen files:** run Python with `-B` or `PYTHONDONTWRITEBYTECODE=1` so no `__pycache__` appears under `interface/` (the manifest test treats any extra file there as a violation).
- **Validation:** every outgoing stage message is checked with `interface/tools/validate.py::check_engine_message` in tests.
