# Question bank format `khqs.bank/1`

A bank is one JSON file. The server loads it at start (`KHQS_BANK=/path/to/bank.json`, default `banks/dev-bank.json`) and refuses to start with a clear error list if it is not valid. Check a file first:

```bash
scripts/check_bank.sh banks/my-bank.json        # prints ERROR / WARNING lines, exit 1 on errors
```

Two sets of eight questions alternate between games (set 0, 1, 0, 1, …). Each set has 3 true/false questions, 3 buzzer questions and 1 final; the 4th act-2 slot is the music question, taken from `tracks` (one track is drawn per game with the game's seeded RNG).

```jsonc
{
  "format": "khqs.bank/1",
  "sets": [
    {
      "id": "set-1",                  // unique
      "musicPosition": 2,              // 1..4: where the music question sits in act 2
      "ox": [ { "id": "q-ox-01", "category": "Monster Biology", "text": "An octopus has three hearts.",
                "answer": "O",         // "O" = true, "X" = false
                "explanation": "Octopuses really do have three hearts." } ],     // exactly 3
      "buzzers": [ { "id": "q-bz-01", "category": "Midnight Superstitions",
                     "text": "At midnight, what should you never look into before bed?",
                     "answer": "Mirror", "aliases": ["The mirror"],             // English; spoken variants
                     "explanation": "The midnight mirror" } ],                   // exactly 3
      "final": { "id": "q-final-01", "category": "Cursed Legends", "text": "…?",
                 "choices": ["…", "…", "…", "…"],        // exactly 4, distinct
                 "answer": "B", "explanation": "…" }
    }
  ],
  "tracks": [                            // one or more (three recommended)
    { "key": "dm",                       // internal name, never sent to the stage or the MC
      "assetId": "a-3f9c1d2e7b40",       // opaque: "a-" + 8..32 lowercase hex; must say nothing about the piece
      "file": "danse_macabre.mp3",       // file name under media/ (tags stripped); the server reads its size
      "durationSec": 30.0,
      "category": "Midnight Concert",    // optional; default "Midnight Concert"
      "text": "What's the title of this piece?",   // optional
      "answer": "Danse Macabre", "aliases": ["Danse Macabre", "Dance Macabre"],
      "explanation": "Saint-Saëns, Danse Macabre",
      "clips": [[0, 7], [0, 16], [0, 30]],      // [startSec, endSec] for hint levels 0, 1, 2; each longer than the last
      "clues": ["private clue for hint 1", "private clue for hint 2"],   // spoken by the MC only, on request; must not contain the title or the composer
      "composer": "Camille Saint-Saëns",     // required; the third spoken hint ("It's by …!"); not in the category, text or a clue
      "credit": { "title": "…", "license": "…", "author": "…", "performer": "…", "source": "https://…" }   // title + license required
    }
  ]
}
```

## Limits (checked)
Category 1–22 characters. OX and buzzer and final text up to 110 characters; choices up to 40. Question ids match `q-[A-Za-z0-9-]+` and are unique across the file. Questions must be answerable by ear: buzzer answers are one to four words.

## What the checks catch
Structure (missing or unknown fields, wrong types); `O`/`X`, `A`–`D`; counts (3 + 3 + 1 per set, 4 choices); limits above; the **answer or an alias hiding in the category or text** (a spoiler on the board); aliases that are empty, repeated or shared with another question's answer; a clue that contains the title or the composer; a missing or empty `composer`; the composer in the category or text; clips that do not get longer or run past `durationSec`; missing media files; duplicate ids or asset ids. A non-English alias is a warning (the game is English only).

## Secrecy
Answers, aliases, explanations, clues, the composer and credits never leave the server before the reveal. `explanation` is shown on the stage after the answer; `credit` only in the music answer reveal. A clue or the composer reaches the MC only when a player asks for a hint and it is granted (docs/GAME_RULES.md §6.2).
