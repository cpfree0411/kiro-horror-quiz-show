"""Question content model and per-game selection.

The real English bank is P4. This module defines the shape, the limits from
docs/GAME_RULES.md section 10, and how one game's eight questions are chosen.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from ..rules.judge import normalize

ASSET_ID = re.compile(r"^a-[0-9a-f]{8,32}$")
QUESTION_ID = re.compile(r"^q-[A-Za-z0-9-]+$")
MAX_CATEGORY = 22
MAX_TEXT = 110
MAX_CHOICE = 40
HINT_LEVELS = 3  # levels 0, 1, 2
DEFAULT_MUSIC_TEXT = "What's the title of this piece?"


@dataclass(frozen=True)
class Credit:
    title: str
    license: str
    author: str | None = None
    performer: str | None = None
    source: str | None = None

    def to_wire(self) -> dict:
        out = {"title": self.title}
        if self.author:
            out["author"] = self.author
        if self.performer:
            out["performer"] = self.performer
        out["license"] = self.license
        if self.source:
            out["source"] = self.source
        return out


@dataclass(frozen=True)
class MusicTrack:
    """A music recording. `asset_id` is opaque; nothing here is sent before the reveal except asset id, size and length."""

    key: str  # internal only, never on the wire
    asset_id: str
    bytes: int
    duration_sec: float
    answer: str
    aliases: tuple[str, ...]
    explanation: str
    clips: tuple[tuple[float, float], ...]  # one (start, end) per hint level 0..2
    clues: tuple[str, ...]  # private MC clue for hint levels 1..2 (never the title)
    credit: Credit
    category: str = "Midnight Concert"
    text: str = DEFAULT_MUSIC_TEXT


@dataclass(frozen=True)
class OxQuestion:
    id: str
    category: str
    text: str
    answer: str  # "O" or "X"
    explanation: str


@dataclass(frozen=True)
class BuzzerQuestion:
    id: str
    category: str
    text: str
    answer: str
    aliases: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class FinalQuestion:
    id: str
    category: str
    text: str
    choices: tuple[str, str, str, str]
    answer: str  # "A".."D"
    explanation: str


@dataclass(frozen=True)
class QuestionSet:
    id: str
    ox: tuple[OxQuestion, ...]  # 3
    buzzers: tuple[BuzzerQuestion, ...]  # 3 regular; the music question is added from a track
    final: FinalQuestion
    music_position: int = 2  # position of the music question within act 2 (1..4)


@dataclass(frozen=True)
class Question:
    """One question of one game, with its place in the show."""

    id: str
    kind: str  # ox | buzzer | av | final
    number: int  # 1..8
    act: int
    index_in_act: int
    category: str
    text: str
    answer: str
    explanation: str
    aliases: tuple[str, ...] = ()
    choices: tuple[str, ...] | None = None
    track: MusicTrack | None = None


@dataclass(frozen=True)
class GameContent:
    set_id: str
    questions: tuple[Question, ...]
    track: MusicTrack

    def act(self, n: int) -> list[Question]:
        return [q for q in self.questions if q.act == n]


@dataclass(frozen=True)
class ContentBank:
    sets: tuple[QuestionSet, ...]
    tracks: tuple[MusicTrack, ...]
    problems: list[str] = field(default_factory=list, compare=False, repr=False)

    def select(self, game_index: int, rng: random.Random) -> GameContent:
        """Sets alternate by game index; the music track is drawn with the seeded RNG."""
        qs = self.sets[game_index % len(self.sets)]
        track = rng.choice(self.tracks)
        questions: list[Question] = []
        n = 0
        for i, q in enumerate(qs.ox, 1):
            n += 1
            questions.append(Question(q.id, "ox", n, 1, i, q.category, q.text, q.answer, q.explanation))
        regular = iter(qs.buzzers)
        for i in range(1, 5):
            n += 1
            if i == qs.music_position:
                questions.append(Question(
                    f"q-av-{n:02d}", "av", n, 2, i, track.category, track.text, track.answer, track.explanation,
                    aliases=track.aliases, track=track))
            else:
                b = next(regular)
                questions.append(Question(b.id, "buzzer", n, 2, i, b.category, b.text, b.answer, b.explanation, aliases=b.aliases))
        f = qs.final
        n += 1
        questions.append(Question(f.id, "final", n, 3, 1, f.category, f.text, f.answer, f.explanation, choices=f.choices))
        return GameContent(qs.id, tuple(questions), track)


def validate_bank(bank: ContentBank) -> list[str]:
    """Return a list of problems (empty = usable). Checks structure and the stage-board limits."""
    p: list[str] = []
    if not bank.sets:
        p.append("no question sets")
    if not bank.tracks:
        p.append("no music tracks")
    ids: set[str] = set()

    def see(qid: str, where: str) -> None:
        if not QUESTION_ID.match(qid):
            p.append(f"{where}: bad question id {qid!r}")
        if qid in ids:
            p.append(f"{where}: duplicate question id {qid!r}")
        ids.add(qid)

    def common(q, where: str, limit_text: bool = True) -> None:
        see(q.id, where)
        if not q.category or len(q.category) > MAX_CATEGORY:
            p.append(f"{where}: category length 1..{MAX_CATEGORY} required ({q.category!r})")
        if not q.text or (limit_text and len(q.text) > MAX_TEXT):
            p.append(f"{where}: text length 1..{MAX_TEXT} required")
        if not q.explanation:
            p.append(f"{where}: explanation required")

    for s in bank.sets:
        if len(s.ox) != 3:
            p.append(f"{s.id}: needs 3 OX questions")
        if len(s.buzzers) != 3:
            p.append(f"{s.id}: needs 3 regular buzzer questions")
        if s.music_position not in (1, 2, 3, 4):
            p.append(f"{s.id}: music_position must be 1..4")
        for q in s.ox:
            common(q, f"{s.id}/{q.id}")
            if q.answer not in ("O", "X"):
                p.append(f"{s.id}/{q.id}: OX answer must be O or X")
        for q in s.buzzers:
            common(q, f"{s.id}/{q.id}")
            if not q.answer.strip():
                p.append(f"{s.id}/{q.id}: answer required")
            if any(not a.strip() for a in q.aliases):
                p.append(f"{s.id}/{q.id}: empty alias")
            shown = normalize(f"{q.category} {q.text}")
            for key in (q.answer, *q.aliases):
                k = normalize(key)
                if len(k) >= 3 and k in shown:
                    p.append(f"{s.id}/{q.id}: the answer or an alias ({key!r}) appears in the category or text")
        f = s.final
        common(f, f"{s.id}/{f.id}")
        if len(f.choices) != 4 or len(set(f.choices)) != 4:
            p.append(f"{s.id}/{f.id}: needs 4 distinct choices")
        if any(not c or len(c) > MAX_CHOICE for c in f.choices):
            p.append(f"{s.id}/{f.id}: each choice 1..{MAX_CHOICE} characters")
        if f.answer not in ("A", "B", "C", "D"):
            p.append(f"{s.id}/{f.id}: final answer must be A..D")
    keys: set[str] = set()
    for t in bank.tracks:
        w = f"track {t.key}"
        if t.key in keys:
            p.append(f"{w}: duplicate key")
        keys.add(t.key)
        if not ASSET_ID.match(t.asset_id):
            p.append(f"{w}: asset id must match a-<8..32 hex>")
        if t.bytes < 1 or t.duration_sec <= 0:
            p.append(f"{w}: bytes and duration must be positive")
        if len(t.clips) != HINT_LEVELS:
            p.append(f"{w}: needs {HINT_LEVELS} clips (levels 0..2)")
        else:
            lens = []
            for a, b in t.clips:
                if not (0 <= a < b <= t.duration_sec):
                    p.append(f"{w}: clip ({a}, {b}) outside 0..{t.duration_sec}")
                lens.append(b - a)
            if lens != sorted(lens):
                p.append(f"{w}: clips must get longer with each hint level")
        if len(t.clues) != HINT_LEVELS - 1:
            p.append(f"{w}: needs {HINT_LEVELS - 1} clues (levels 1..2)")
        if not t.answer.strip() or not t.explanation.strip():
            p.append(f"{w}: answer and explanation required")
        if not t.credit.title or not t.credit.license:
            p.append(f"{w}: credit needs title and license")
        if not t.category or len(t.category) > MAX_CATEGORY:
            p.append(f"{w}: category length 1..{MAX_CATEGORY}")
        shown = normalize(f"{t.category} {t.text}")
        for key in (t.answer, *t.aliases):
            k = normalize(key)
            if len(k) >= 3 and k in shown:
                p.append(f"{w}: the title or an alias ({key!r}) appears in the category or text")
        norm_title = t.answer.casefold()
        for c in t.clues:
            if norm_title and norm_title in c.casefold():
                p.append(f"{w}: a clue contains the title")
    return p
