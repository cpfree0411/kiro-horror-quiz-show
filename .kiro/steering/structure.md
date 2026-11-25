---
inclusion: always
---

# Repository structure

| Path | Owner | Rule |
| --- | --- | --- |
| `stage/` | visual owner | Frozen. Served as is |
| `interface/` | visual owner | Frozen. Protocol spec, schema, scenarios, validator |
| `media/` | shared | Question music excerpts + `CREDITS.md`. Add only with recorded license/source |
| `docs/` | shared | `HANDOFF.md`, `GAME_RULES.md` are the inputs; add your own design notes beside them |
| `.kiro/specs/` | Kiro | Requirements, design, tasks per feature |
| `server/` (name is Kiro's choice) | Kiro | Engine, server, MC adapter, connector, phone UI |
| `tests/` | Kiro | Unit, protocol, end-to-end |
| `MANIFEST.sha256` | visual owner | Hashes of `stage/` and `interface/`; a test checks it |

- Keep the engine pure (no I/O, injectable clock and RNG) and the adapters thin: WebSocket server, MC adapter (live / mock), asset server, connector.
- Grow by adding adapters behind small interfaces; do not add abstractions before a second real use needs them.
- Tech stack is open. The proven reference is Python asyncio + an ASGI server, one process, one worker, memory-only state, `google-genai` for Gemini Live, Playwright for end-to-end tests. Write your choice in `tech.md`.
