"""Deterministic local answer judging (docs/GAME_RULES.md section 9.3).

The model never judges. `heard` may be English or Korean; aliases cover both.
"""
from __future__ import annotations

import difflib
import unicodedata
from collections.abc import Iterable

FUZZY_RATIO = 0.8
SUBSTRING_MIN_LEN = 3
FUZZY_MIN_LEN = 4


def normalize(text: str) -> str:
    """NFKC, case-fold, keep only letters, digits and combining marks (drops spaces, punctuation, symbols)."""
    s = unicodedata.normalize("NFKC", text).casefold()
    s = unicodedata.normalize("NFKC", s)
    return "".join(ch for ch in s if unicodedata.category(ch)[0] in "LNM")


def _keys(answer: str, aliases: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for raw in (answer, *aliases):
        k = normalize(raw)
        if k and k not in seen:
            seen.append(k)
    return seen


def _fuzzy_hit(heard: str, key: str) -> bool:
    n = len(key)
    for width in (n - 1, n, n + 1):
        width = min(width, len(heard))
        if width < 1:
            continue
        for i in range(len(heard) - width + 1):
            if difflib.SequenceMatcher(None, heard[i : i + width], key).ratio() >= FUZZY_RATIO:
                return True
    return False


def answer_matches(heard: str, answer: str, aliases: Iterable[str] = (), kind: str = "buzzer") -> bool:
    """True if `heard` is a correct answer.

    All kinds: exact match after normalisation against the answer or any alias.
    kind == 'av' (music) only: also a key of length >= 3 contained in the heard text,
    or a sliding window of the heard text with difflib ratio >= 0.8 against a key of length >= 4.
    """
    h = normalize(heard)
    if not h:
        return False
    keys = _keys(answer, aliases)
    if h in keys:
        return True
    if kind != "av":
        return False
    for k in keys:
        if len(k) >= SUBSTRING_MIN_LEN and k in h:
            return True
    for k in keys:
        if len(k) >= FUZZY_MIN_LEN and _fuzzy_hit(h, k):
            return True
    return False
