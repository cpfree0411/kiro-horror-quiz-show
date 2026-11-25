---
inclusion: always
---

# Language and voice

- **English everywhere a user can see or hear it:** stage strings, phone UI, operator controls, error messages, questions, choices, categories, explanations, MC speech, captions, README.
- **English only (owner decision, 2026-11-26).** Players speak English; the MC speaks English and does not need to understand Korean. Player names may be typed in any script; show them exactly as typed; the MC says them as given and never adds nicknames or honorifics.
- Keep the language choice in one place (`server/khqs/mc/prompts.py` + content files), so another edition can swap content and prompt, not engine code.
- Spoken answers are captured by a tool call from the MC: `heard` = **exactly what the player said, verbatim, never corrected or completed**; `recognition` = `clear | unclear` (understood or not — not correct or not).
- The engine judges with the deterministic local `answer_matches` (`docs/GAME_RULES.md` §9.3). The model never judges correctness and never sees the answer or aliases before the reveal.
- Aliases are English. The music question is lenient (title is enough, small slips allowed); everything else is exact after normalisation.
- Recognition failure is not a wrong answer: ask again; after two failures, open a text box on that player's phone.
- Reveals wait for the MC's audio to actually finish playing (output playback cursor), not for generation to finish.
- During the music clip the MC is silent and the mic is closed. On a buzz: flush browser MC audio and interrupt Live immediately.
