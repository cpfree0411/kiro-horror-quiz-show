# P3 — Gemini Live MC and the loadable question bank: requirements

Sources: `docs/HANDOFF.md` §4–§8, §11 (P3), `docs/GAME_RULES.md` §6.1, §8, §9, §11, steering `secrecy-and-safety.md` and `language-and-voice.md`, owner answers after P2, and two owner scope changes: **English only** (no Korean understanding) and **P3 is the last phase of this agent**, so P3 also delivers the question bank as a data file and leaves the repo handoff-ready.

## Out of scope
Writing the real English bank (the next agent does it; P3 delivers the format, loader, validator and a converted dev bank). Submission packaging.

## Requirements

### A. Question bank file
| # | Requirement |
| --- | --- |
| A1 | A documented JSON format `khqs.bank/1` (`docs/QUESTION_BANK_FORMAT.md`) covers every field the engine needs, including the music slot (asset id, file, duration, hint clips, private clues, credit). |
| A2 | The server loads the bank named by `KHQS_BANK`; without it, `banks/dev-bank.json`. An invalid bank stops startup with a clear error list. |
| A3 | `scripts/check_bank.sh <file>` validates a bank with the rules §10 limits, the answer-in-category/text scan, alias checks and file checks, prints `ERROR`/`WARNING` lines and exits 1 on errors. |
| A4 | The dev bank is converted to the file format; its aliases are English only. |

### B. Live session
| # | Requirement |
| --- | --- |
| B1 | The key is read from the configured env file only when a session connects, kept in memory, and never printed, logged, copied, sent to a browser, or committed. Error text from the SDK is sanitized. |
| B2 | One live session at a time. No automatic reconnect loop: a lost or failed session leaves the MC **offline** and the show continues without voice; the operator reconnects explicitly. The only internal re-connection is the GoAway/session-resumption handoff, at most 4 times. |
| B3 | Caps: session 40 min; 240 s with no MC activity; 35 s response/playback stall → safe stop. |
| B4 | Starting a live session needs a loopback stage listener (guard in settings) and an explicit operator action (`POST /api/mc/connect` or START in live mode). Real sessions are counted (`sessions_opened`) and optionally appended to a log file (time and purpose only). |
| B5 | Tests never open a live session: a fake transport implements the same interface. |

### C. Speaking, playback cursor, status
| # | Requirement |
| --- | --- |
| C1 | Each engine `McSay` becomes one model turn built from the cue's whitelisted facts only (`prompts.py`). Turns are sent in order. |
| C2 | Audio goes to the stage page tagged with the token. The browser reports `started` and `played` from real audio output; only then does the engine see `mc_started` / `mc_played`. Generation finishing is not playback finishing. |
| C3 | `mc.status` follows real playback: `speaking` on `mc_started`, `idle` on `mc_played`/stale/failed (for the live MC; the mock keeps issue-time status). |
| C4 | A buzz (`McInterrupt`) flushes browser audio at once, drops queued lines, discards audio of the interrupted turn until the provider's `interrupted`/`turn_complete`, and treats a late `turn_complete` after `interrupted` as normal. |
| C5 | Music: no MC turn or mic audio between `av.play` and the clip's end (engine contract, kept). |
| C6 | `mc.caption` comes from the model's output transcription through the engine's secret filter; player speech is never captioned. |

### D. Listening
| # | Requirement |
| --- | --- |
| D1 | The mic opens only while the engine has an open `McListen` and the MC is not speaking; the browser forwards no audio otherwise. Echo cancellation stays off. |
| D2 | Audio is held back locally until it is voiced; `activity_start` and the audio go to Live only then. A silent window never touches Live and ends as a recognition failure (`unclear`, not voiced) after a short silence limit. |
| D3 | Voiced evidence is measured on the PCM actually forwarded (RMS floor and minimum duration). |
| D4 | Answers arrive as tool calls: `report_answer(heard, recognition)`, `report_reason(heard)`, `report_decision(decision)`. `heard` is verbatim. Tool results back to the model are a silent `{received: true}` and nothing else. |
| D5 | A missing tool call after the speech ended is a recognition failure. The engine decides correctness; the model is never asked to. |

### E. Secrecy
| # | Requirement |
| --- | --- |
| E1 | No text sent to Live before a reveal contains an answer, alias, explanation, clue (except in the hint turn) or credit. Tested by recording every string sent through the fake transport and scanning it with the P1 scanner rules. |
| E2 | Tool results contain only `{received: true}`. |
| E3 | The system prompt forbids revealing, hinting, judging, nicknames and shaming words, and says the MC never knows an answer. |

### F. Browser
| # | Requirement |
| --- | --- |
| F1 | `KHQS_HOST` exists once the MC audio starts: `audioContext` (the stage's), `mcOutputNode`, `onMcPlayback`, `stopMc`, `setMicGate`. |
| F2 | START in live mode gets mic permission, opens the MC socket and connects the session before the show starts. Failure writes `MIC NEEDED` or `MC OFFLINE — TRY AGAIN` into the lobby error element and re-enables the start sign. |
| F3 | The chip shows MC state (offline / connecting / online) and offers RECONNECT MC (explicit). |
| F4 | The pad panel is collapsible to a small edge tab, collapsed by default when every joined player has a phone socket, and never covers NEW SHOW or the stage's own buttons. |

### G. Docs and handoff
| # | Requirement |
| --- | --- |
| G1 | English-only scope applied to `docs/GAME_RULES.md`, `docs/HANDOFF.md` and `.kiro/steering/*.md`; the frozen interface file is not edited. |
| G2 | README current (run steps, ports, settings incl. live MC and bank, bank format, known limits); specs and `verification.md` up to date; everything pushed; `git status` clean. |

### H. Acceptance
| # | Requirement |
| --- | --- |
| H1 | Unit tests with a fake Live transport cover B–E. |
| H2 | A browser test drives a full solo game through the real browser audio host and `/ws/mc` with the fake transport (no API). |
| H3 | A real end-to-end smoke run (free tier, deliberate, sessions counted) with a headless browser and a fake microphone file. |
| H4 | The owner plays with a real voice (not done by this agent; listed as pending). |
