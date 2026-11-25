"""Secret filter for `mc.caption` (interface section 12.2, docs/GAME_RULES.md section 8).

Best effort by design: it blocks the answer, aliases, correct choice text and explanation
(including partial leading words), and assertion forms of one-letter answers. The MC is also
told not to reveal; this is the second line of defence. Never feed it player speech.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .judge import normalize

STRONG = {"answer", "correct", "correctly", "right", "truth"}
WEAK = {"is", "its", "it's", "thats", "that's"}  # only directly before the option
OX_FORMS = {"o", "oh", "x", "ex", "circle", "cross", "true", "false"}
LETTER_FORMS = {"a", "b", "c", "d", "ay", "bee", "see", "dee"}
MAX_CAPTION = 300
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class CaptionSecrets:
    phrases: tuple[str, ...] = ()  # answer, aliases, explanation, correct choice text
    letter_kind: str | None = None  # "ox" | "letters" while a one-letter answer is unrevealed
    block_all: bool = False  # e.g. a buzzer question is being read


def _tokens(text: str) -> list[str]:
    return [t.strip(".,!?;:\"'()[]").lower().replace("\u2019", "'") for t in text.split()]


def _letter_assertion(text: str, kind: str) -> bool:
    forms = OX_FORMS if kind == "ox" else LETTER_FORMS
    toks = [t for t in _tokens(text) if t]
    for i, t in enumerate(toks):
        if t in STRONG and any(x in forms for x in toks[i + 1 : i + 5]):
            return True
        if kind == "ox" and t in WEAK and i + 1 < len(toks) and toks[i + 1] in forms:
            return True
    return False


def trips(text: str, s: CaptionSecrets) -> bool:
    n = normalize(text)
    for p in s.phrases:
        k = normalize(p)
        if len(k) >= 2 and k in n:
            return True
    return bool(s.letter_kind) and _letter_assertion(text, s.letter_kind)


def _held_words(words: list[str], phrases: tuple[str, ...]) -> int:
    """How many trailing words could be the start of a multi-word secret phrase."""
    nw = [normalize(w) for w in words]
    best = 0
    for p in phrases:
        pw = [normalize(w) for w in _WORD.findall(p)]
        pw = [w for w in pw if w]
        for k in range(min(len(pw) - 1, len(nw)), 0, -1):
            if nw[-k:] == pw[:k]:
                best = max(best, k)
                break
    return best


@dataclass
class _Utterance:
    blocked: bool = False
    sent: str = ""


@dataclass
class CaptionFilter:
    _u: dict[str, _Utterance] = field(default_factory=dict)

    def process(self, uid: str, text: str, final: bool, secrets: CaptionSecrets) -> str | None:
        """Return the (cumulative) text that may be sent, or None to send nothing."""
        u = self._u.setdefault(uid, _Utterance())
        if u.blocked or secrets.block_all:
            return None
        if trips(text, secrets):
            u.blocked = True
            return None
        out = text.strip()
        if not final:
            if out and not text[-1:].isspace() and not out[-1] in ".!?,;:":
                out = out[: out.rfind(" ")] if " " in out else ""
            words = _WORD.findall(out)
            held = _held_words(words, secrets.phrases)
            if held:
                out = " ".join(words[: len(words) - held])
        if len(out) > MAX_CAPTION:
            out = out[:MAX_CAPTION].rsplit(" ", 1)[0]
        if not out or (out == u.sent and not final):
            return None
        u.sent = out
        if final:
            self._u.pop(uid, None)
        return out
