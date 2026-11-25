# P3 — design

## Pieces
```
 engine ──McSay/McListen/McInterrupt/McStopListen/McMic──► LiveMc (server/khqs/mc/live.py)
                                                         │  prompts.py: cue + facts → one English turn
                                                         │  voice.py:   VoiceMeter (RMS evidence, end of speech)
                                                         ▼
                                       LiveTransport (Protocol) ── GeminiTransport (google-genai) / FakeTransport (tests)
 browser  ◄── /ws/mc (JSON down: audio b64 per token, end, flush, mic; binary up: mic PCM 16 kHz; JSON up: started/played)
   mc-audio.js: KHQS_HOST, playback scheduler (24 kHz PCM on the stage's AudioContext), mic capture (worklet)
```
`LiveMc.handle(effect)` is called by the host like the mock MC. Browser reports reach the engine through `host.run(engine.mc_started | mc_played)`.

## LiveTransport events
`AudioOut(pcm)`, `OutText(text)`, `ToolCall(id, name, args)`, `Interrupted`, `TurnComplete`, `GoAway(seconds)`, `ResumeHandle(handle)`, `Closed(reason)`. Methods: `connect(system_prompt, resume)`, `send_turn(text)` (a model turn is requested), `send_context(text)` (no response requested), `send_audio(pcm16k)`, `activity(start)`, `tool_result(call_id, name)` (silent), `close()`.

## Turn queue
Says are queued FIFO. The adapter sends the next turn when the previous one completed generation (`TurnComplete`), so the browser holds ordered per-token audio. Each token is `started`/`played` by the browser. An interrupt drops the queue and sets `discard` until `Interrupted` or `TurnComplete`; the next `send_turn` also interrupts generation on the provider side. Events in any order are tolerated.

## Listening
`McListen` opens a window: `send_context("[LISTEN …]")`, then when the MC is idle (queue empty, all tokens played) the browser mic opens. PCM chunks go through `VoiceMeter`: held until voiced (≥ 0.012 RMS for ≥ 160 ms), then `activity(start)` + the held audio + live audio are sent. After speech (≥ 700 ms silence) or 16 s, `activity(end)` and the mic closes; the model must call the tool within 6 s, otherwise recognition failure. No voiced audio within 7 s → failure without touching Live. Engine failure handling (ask again, two failures → phone text box) is unchanged from P1.

## Prompts
One module holds the persona, the language ("English") and a builder per cue. Turn text is `[CUE name]` + short stage directions + the cue facts. The system prompt says: never reveal or hint, never judge, report `heard` verbatim, call the tool once and say nothing after it, one or two short sentences, say names as typed, no nicknames, never use shaming words.

## Failure and offline mode
Any unexpected close, error, cap or stall → `safe_stop(reason)`: fail pending tokens, tell the engine the MC is offline (`engine.mc_offline()`: says resolve at once, no listens, holder gets the text box), close the browser socket's audio. The show continues. `POST /api/mc/connect` opens a fresh session (context is not carried; every cue is self-contained) and `engine.mc_online()`.

## Server additions
`/ws/mc` (stage app only, origin guarded, one socket), `POST /api/mc/connect`, `POST /api/mc/disconnect`, `GET /api/mc/status`. `/api/start` in live mode requires an online MC. Settings: `KHQS_MC=mock|live`, `KHQS_ENV_FILE` (default `/home/na/.config/jarvis-live/.env`), `KHQS_LIVE_MODEL` (default `gemini-3.8-live`), `KHQS_LIVE_VOICE` (default `Despina`), `KHQS_LIVE_LOG`. Live raises the default buzzer window to 60 s.

## Browser
`/play/mc-audio.js` is loaded by `link.js` when the config says `mc: live`. Playback: each chunk becomes an `AudioBuffer`, scheduled back to back on the stage's `AudioContext`; `started` fires when a token's first buffer starts, `played` when its last ends; `stopMc()` stops all sources without reporting flushed tokens. Capture: a 16 kHz `AudioContext`, a worklet that emits 20 ms Int16 frames, sent only while the server says the mic is open and no `setMicGate` reason is closed. getUserMedia with echo cancellation, noise suppression and AGC off.

## Bank file
`khqs.bank/1`, see `docs/QUESTION_BANK_FORMAT.md`; `content/bank_io.py` parses and validates, `content/check.py` is the command, `banks/dev-bank.json` is the converted dev bank.

## Decisions
| Topic | Decision |
| --- | --- |
| Manual activity detection | On. Push-to-talk style windows set by the engine remove false triggers and echo; also keeps silent windows off the API. |
| Model | `gemini-3.8-live` (what the prototype proved), configurable. |
| Offline fallback | Continue without voice rather than stop the show. |
| mc.status for live | Playback-driven (owner decision); mock keeps issue-time. |
| Heard text length | Capped at 200 characters. |
