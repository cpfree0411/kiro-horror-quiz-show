# P0 — design

## Decisions

| Topic | Decision | Reason |
| --- | --- | --- |
| Copy method | `tar` pipe with two `--exclude`; then `diff -r` against the source | Preserves bytes and modes; the diff proves only the two excluded files differ. |
| Line endings | `.gitattributes`: `* -text` | A CRLF/LF conversion would break the manifest; this makes git store bytes as they are. |
| Language | Python 3.12 (already managed by `uv` on this host), asyncio | Matches the handoff's proven reference stack; `validate.py` is Python. |
| Venv | `/srv/workdata/projects/.venvs/kiro-horror-quiz-show` (same folder the other projects use) | R9. |
| Caches | `uv --cache-dir /srv/workdata/cache/uv`, `pytest -o cache_dir=/srv/workdata/build-cache/khqs-pytest`, `PLAYWRIGHT_BROWSERS_PATH` set inside `scripts/test.sh` | Per-tool, no global overrides (R9). |
| Playwright | Python package pinned to 1.64.1 | Its Chromium revision (1248) is already cached; 1.65.x wants 1255, which is not, and we do not download browsers. |
| Manifest test | Pure-Python verifier (`tests/manifest_check.py`) + `sha256sum -c` test + tamper self-test | Portable, catches extra files, and the checker is proven not vacuous. |
| `-B` / no bytecode | `conftest.py` sets `sys.dont_write_bytecode`; scripts set `PYTHONDONTWRITEBYTECODE` | A `__pycache__` under `interface/tools/` would count as an extra frozen file. |
| Demo check | Playwright test with marker `slow`, excluded by default (`-m 'not slow'`), static `http.server` on `127.0.0.1:<ephemeral>` | R6 takes ~5 min real time; ephemeral loopback port touches no reserved port. |
| Ports | Stage + MC `127.0.0.1:18830`, phones `<LAN address>:18831` | Verified free with `ss -ltn`; neither reserved. Nothing binds them in P0. |
| Git identity | Repo-local `cpfree0411` + GitHub noreply address | No global identity exists; the old prototype's `Gemini` identity is not ours to reuse. |
| Remote | `gh repo create cpfree0411/kiro-horror-quiz-show --private` | R7. |

## Files added in P0
`.gitignore`, `.gitattributes`, `pyproject.toml`, `README.md`, `.kiro/steering/tech.md`, `.kiro/specs/p0-bootstrap/*`, `scripts/setup_dev.sh`, `scripts/test.sh`, `tests/{conftest,manifest_check,test_frozen_boundary,test_repo_hygiene}.py`, `tests/e2e/test_stage_demo_static.py`.
