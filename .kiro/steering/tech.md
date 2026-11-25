---
inclusion: always
---

# Tech stack

Chosen in P0 (see `.kiro/specs/p0-bootstrap/design.md`). The handoff leaves the stack open; this is the proven reference stack.

- **Language / runtime:** Python 3.12 (`requires-python >= 3.12`), asyncio, one process, one worker, memory-only state.
- **Server (P2):** Starlette on uvicorn (WebSocket via `websockets`), one process and one event loop, two listeners: stage on `127.0.0.1:18830` (everything), phones on the LAN address `:18831` (phone routes only). Run with `scripts/run.sh`.
- **MC (P3):** `google-genai` for Gemini Live behind a small transport interface (`server/khqs/mc/transport.py`); `LiveMc` owns the turn queue, playback cursor, listening and caps. The mock MC (same playback-cursor contract) is the default and the only MC tests use; a fake transport stands in for the SDK.
- **Question bank:** a JSON file (`docs/QUESTION_BANK_FORMAT.md`), validated by `scripts/check_bank.sh`; `KHQS_BANK` selects it.
- **Tests:** pytest. Browser end-to-end tests use Playwright for Python, pinned to 1.64.1 to match the Chromium builds cached in `/srv/workdata/browser-cache/ms-playwright`.
- **Layout:** `server/` holds the engine (pure, no I/O, injectable clock and RNG) and the thin adapters. `tests/` holds unit, protocol and end-to-end tests. `scripts/` holds dev helpers.
- **Dev environment on the owner's host:** the venv lives outside the repo at `/srv/workdata/projects/.venvs/kiro-horror-quiz-show`. Cache locations are passed per tool (`uv --cache-dir`, `pytest -o cache_dir`, `PLAYWRIGHT_BROWSERS_PATH` inside `scripts/test.sh`), never set as global environment overrides. Use `scripts/setup_dev.sh` and `scripts/test.sh`.
- **Frozen files:** run Python with `-B` or `PYTHONDONTWRITEBYTECODE=1` so no `__pycache__` appears under `interface/` (the manifest test treats any extra file there as a violation).
- **Validation:** every outgoing stage message is checked with `interface/tools/validate.py::check_engine_message` in tests.
