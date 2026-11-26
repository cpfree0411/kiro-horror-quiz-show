# P7 — Asking for a hint in the music question: requirements

Source: the owner's live-voice play test ("nearly perfect") and the P7 prompt. Idea in the owner's words: in the music quiz a player buzzes and says "it's too hard, give me a hint", the MC asks the other players whether they agree, then gives the hint. There is no second song. `stage/` and `interface/` are frozen (the act-1 reveal sound, commit `faa43b1`, was made by the other agent). Rules as before: spec first, never print or log the Gemini key, tests never call the live API, no server on 18830/18831, stop and report at the end.

## 1. Automatic ladder (changed)
| # | Requirement |
| --- | --- |
| A1 | Clip levels 0 to 2 and their clips are unchanged. After a failed level (everyone wrong, or the open window times out) the clip gets longer exactly as today, through the same `av.hint` gate. |
| A2 | The automatic step no longer speaks a clue. The MC says one short line ("a longer listen"). The end of the ladder (suspense and reveal after level 2) is unchanged. |
| A3 | Spoken hints come only on request (section 2). |

## 2. Asking for a hint
| # | Requirement |
| --- | --- |
| R1 | A player who holds the buzzer in the music question (during the clip or after it, at any level) can ask for a hint instead of answering. |
| R2 | By voice: the live MC reports what it heard, verbatim, through `report_answer`. The model does not decide. The engine decides locally whether the heard text is a hint request, with a small English phrase list. |
| R3 | A heard text that matches the answer (by the existing judge) is always an answer, never a hint request. |
| R4 | By phone: a HINT button next to the answer field (and on the voice screen) while the player holds the buzzer. The same engine path serves voice and button. |
| R5 | A request is valid only in the music question, for the holder, before an answer was given. A hint request is not an answer: it is not final, it does not lock the player out and it ends no window by itself. |

## 3. Consent
| # | Requirement |
| --- | --- |
| C1 | With two or three players (at least one other connected player) the MC asks the others in one short, playful line whether they agree. The engine opens a consent window of about 8 s (`hint_consent_ms`). |
| C2 | Agree: yes, sure, okay, go ahead, fine and similar. Refuse: no, nope, never, no way and similar. Any refusal refuses. Classification is local, on the verbatim text. |
| C3 | Silence or unclear speech until the window ends counts as agree (the MC may joke "Silence means yes!"). |
| C4 | Phones of the others show AGREE / NO during the window. A phone vote and a spoken vote use the same engine path. A NO refuses at once. When every other player has voted yes, the window ends early. |
| C5 | Solo (nobody else connected): no window. The MC grants the hint with a joke. |

## 4. Granted and refused
| # | Requirement |
| --- | --- |
| G1 | Granted: the MC gives the next hint, two sentences at most and never the title, in this order: clue 1, clue 2, the composer ("It's by Edvard Grieg!"). |
| G2 | The requester then answers at once, still holding the buzzer, with the normal answer window. Right is +20 as usual. Wrong locks the requester out as usual. After that the round goes on as today (buzzers reopen for the others, or the ladder continues). |
| G3 | Refused: the MC teases briefly ("Denied! You're on your own."). The requester must answer now, without a hint, with the normal answer window and the normal rules. |
| G4 | At most three spoken hints per music question (clue 1, clue 2, composer). A request after that gets "No hints left!" and the player must answer. |
| G5 | Each player may ask once per music question. A refused request counts as asked, but not as a hint given. A second request by the same player gets "One hint per player!" (owner's answer after P7; "No hints left!" stays for the case where all three are out), then the player must answer; a further hint phrase in that window is simply an answer. |

## 5. Privacy
| # | Requirement |
| --- | --- |
| V1 | The model never sees a title, alias or explanation before the reveal. A clue or the composer goes to the MC only at the moment it is granted (in the `hint_grant` cue facts). |
| V2 | The stage stream, snapshots and phone views never contain a clue or the composer before the reveal, except the MC caption of the granted line (the caption filter lets the granted composer pass, nothing else). |
| V3 | Votes and hint state are never in the stream. Phones see only what they need. |

## 6. Bank
| # | Requirement |
| --- | --- |
| B1 | khqs.bank/1 gets a required `composer` string per track: format doc, loader, validator, `check_bank`. A composer that appears in the category or text, or in a clue, is an error. |
| B2 | `banks/en-bank.json`: add exactly `dm: "Camille Saint-Saëns"`, `hk: "Edvard Grieg"`, `tf: "Johann Sebastian Bach"`; nothing else in that file changes. The dev bank gets the same values. `tests/test_en_bank.py` may check the composer. |

## 7. Stage
S1. No edit to `stage/` or `interface/`. Report what the existing wire messages show for a hint request, the consent window, and a granted or refused hint. If a visible cue would clearly help, write down exactly what it needs (event, fields, when it appears and disappears).

## 8. Reports and verification
- Worst-case length of the music question with mock MC timings (all hints asked, refused, then granted; every level failing), compared with today.
- The new MC prompt lines and tool definitions (exact text), and the phrase lists.
- Unit tests: request at each level and during the music; consent agree, refuse, silence, solo; requester right and wrong after the hint; the hint limit and the once-per-player limit; an answer that also contains "hint"; `assert_no_leaks` over full games that use hints; the fast suite, `check_all_quick.sh`, `check_banks.sh`, the manifest; one slow browser game using the HINT button through the phone (mock MC).
