---
inclusion: always
---

# Language and voice

- **English everywhere a user can see or hear it:** stage strings, phone UI, operator controls, error messages, questions, choices, categories, explanations, MC speech, captions, README.
- **Players may speak Korean or English.** The MC understands both and always answers in English. Player names may be in Hangul; show them exactly as typed; the MC may romanise them when speaking but never adds nicknames or honorifics.
- Keep the language choice in one place (MC system prompt + content files), so a Korean edition can be made later by swapping content and prompt, not by editing engine code.
- Spoken answers are captured by a tool call from the MC: `heard` = **exactly what the player said, in the language they said it, never translated**; `recognition` = `clear | unclear` (understood or not — not correct or not).
- The engine judges with the deterministic local `answer_matches` (`docs/GAME_RULES.md` §9.3). The model never judges correctness and never sees the answer or aliases before the reveal.
- Aliases cover English and Korean forms. The music question is lenient (title is enough, small slips allowed); everything else is exact after normalisation.
- Recognition failure is not a wrong answer: ask again; after two failures, open a text box on that player's phone.
- Reveals wait for the MC's audio to actually finish playing (output playback cursor), not for generation to finish.
- During the music clip the MC is silent and the mic is closed. On a buzz: flush browser MC audio and interrupt Live immediately.
