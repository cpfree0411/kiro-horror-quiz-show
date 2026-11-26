"""Local classification of what a player said about a hint (docs/GAME_RULES.md section 6.2).

The model reports the words verbatim and never decides. This module decides, on plain English phrase lists (P7).
"""
from __future__ import annotations

import re
import unicodedata

from .judge import answer_matches

# --- a player asks for a hint (instead of answering)
HINT_WORDS = frozenset({"hint", "hints", "clue", "clues", "help"})
HINT_PHRASES = ("too hard", "too difficult", "so hard", "so difficult", "i give up", "give up")

# --- the others answer the MC's "do you agree?"
AGREE_WORDS = frozenset({"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "fine", "agree", "agreed", "alright", "ya", "yea", "aye"})
AGREE_PHRASES = ("go ahead", "of course", "why not", "all right", "go for it", "i agree", "sounds good", "no problem", "no worries",
                 "not a problem", "i do not mind", "i dont mind", "do not mind", "dont mind")
REFUSE_WORDS = frozenset({"no", "nope", "nah", "never", "refuse", "disagree", "denied", "negative"})
REFUSE_PHRASES = ("no way", "not really", "absolutely not", "i do not agree", "i dont agree", "not a chance", "no thanks", "no thank you",
                  "do not think so", "dont think so", "do not give", "dont give", "dont do it", "do not do it")

AGREE, REFUSE, UNCLEAR = "agree", "refuse", "unclear"


def _words(text: str) -> str:
    """Lower-case words separated by single spaces; apostrophes vanish (don't -> dont)."""
    s = unicodedata.normalize("NFKC", text).casefold().replace("'", "").replace("\u2019", "")
    return " ".join(re.sub(r"[^\w]+", " ", s).split())


def _has(words: str, phrase: str) -> bool:
    return f" {phrase} " in f" {words} "


def looks_like_hint_request(heard: str) -> bool:
    w = _words(heard)
    return bool(w) and (any(x in HINT_WORDS for x in w.split()) or any(_has(w, p) for p in HINT_PHRASES))


def is_hint_request(heard: str, answer: str, aliases=(), kind: str = "av") -> bool:
    """A hint request, unless the heard text is also an answer: an answer always wins."""
    if not isinstance(heard, str) or not heard.strip():
        return False
    if answer_matches(heard, answer, aliases, kind):
        return False
    return looks_like_hint_request(heard)


def classify_consent(heard: str) -> str:
    """agree | refuse | unclear. Any refusal refuses; polite 'no problem' and 'I don't mind' are agreement."""
    if not isinstance(heard, str):
        return UNCLEAR
    w = _words(heard)
    if not w:
        return UNCLEAR
    agree = False
    for p in AGREE_PHRASES:  # take agreeing phrases out first, so "no problem" does not read as "no"
        if _has(w, p):
            agree = True
            w = _words(w.replace(p, " "))
    toks = w.split()
    if any(t in REFUSE_WORDS for t in toks) or any(_has(w, p) for p in REFUSE_PHRASES):
        return REFUSE
    if agree or any(t in AGREE_WORDS for t in toks) or any(_has(w, p) for p in AGREE_PHRASES):
        return AGREE
    return UNCLEAR
