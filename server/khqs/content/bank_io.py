"""Question bank files (format `khqs.bank/1`, documented in docs/QUESTION_BANK_FORMAT.md).

`load_bank` reads a JSON file and returns a ContentBank; `check_bank_file` returns every problem it can find
(structure first, then the content checks in model.validate_bank, then extra alias checks).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from ..rules.judge import normalize
from .model import (ASSET_ID, BuzzerQuestion, ContentBank, Credit, FinalQuestion, MusicTrack, OxQuestion, QuestionSet,
                    validate_bank)

FORMAT = "khqs.bank/1"
HANGUL = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")

OX_KEYS = {"id", "category", "text", "answer", "explanation"}
BUZZER_KEYS = {"id", "category", "text", "answer", "aliases", "explanation"}
FINAL_KEYS = {"id", "category", "text", "choices", "answer", "explanation"}
SET_KEYS = {"id", "musicPosition", "ox", "buzzers", "final"}
TRACK_KEYS = {"key", "assetId", "file", "durationSec", "category", "text", "answer", "aliases", "explanation", "clips", "clues", "credit"}
TRACK_REQUIRED = TRACK_KEYS - {"category", "text"}
CREDIT_KEYS = {"title", "license", "author", "performer", "source"}
TOP_KEYS = {"format", "sets", "tracks"}


class BankError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def _shape(obj, keys: set[str], required: set[str], where: str, out: list[str]) -> bool:
    if not isinstance(obj, dict):
        out.append(f"{where}: must be an object")
        return False
    for k in sorted(set(obj) - keys):
        out.append(f"{where}: unknown field {k!r}")
    for k in sorted(required - set(obj)):
        out.append(f"{where}: missing field {k!r}")
    return True


def _str(obj, key, where, out, optional=False):
    v = obj.get(key)
    if v is None and optional:
        return None
    if not isinstance(v, str) or not v.strip():
        out.append(f"{where}.{key}: must be a non-empty string")
        return ""
    return v


def _strs(obj, key, where, out):
    v = obj.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        out.append(f"{where}.{key}: must be a list of strings")
        return ()
    return tuple(v)


def parse_bank(data, media_dir: Path) -> tuple[ContentBank | None, list[str]]:
    """Structure -> ContentBank. Returns (bank or None, problems)."""
    out: list[str] = []
    if not _shape(data, TOP_KEYS, TOP_KEYS, "bank", out):
        return None, out
    if data.get("format") != FORMAT:
        out.append(f"bank.format: must be {FORMAT!r}")
    sets, tracks = [], []
    for si, s in enumerate(data.get("sets") or []):
        w = f"sets[{si}]"
        if not _shape(s, SET_KEYS, SET_KEYS, w, out):
            continue
        w = f"set {s.get('id', si)}"
        ox, bz = [], []
        for i, q in enumerate(s.get("ox") or []):
            if _shape(q, OX_KEYS, OX_KEYS, f"{w}.ox[{i}]", out):
                ox.append(OxQuestion(*(_str(q, k, f"{w}.ox[{i}]", out) for k in ("id", "category", "text", "answer", "explanation"))))
        for i, q in enumerate(s.get("buzzers") or []):
            if _shape(q, BUZZER_KEYS, BUZZER_KEYS - {"aliases"}, f"{w}.buzzers[{i}]", out):
                bz.append(BuzzerQuestion(_str(q, "id", f"{w}.buzzers[{i}]", out), _str(q, "category", f"{w}.buzzers[{i}]", out),
                                         _str(q, "text", f"{w}.buzzers[{i}]", out), _str(q, "answer", f"{w}.buzzers[{i}]", out),
                                         _strs(q, "aliases", f"{w}.buzzers[{i}]", out), _str(q, "explanation", f"{w}.buzzers[{i}]", out)))
        f = s.get("final")
        final = None
        if _shape(f, FINAL_KEYS, FINAL_KEYS, f"{w}.final", out):
            ch = f.get("choices")
            if not isinstance(ch, list) or not all(isinstance(c, str) for c in ch):
                out.append(f"{w}.final.choices: must be a list of 4 strings")
                ch = []
            final = FinalQuestion(_str(f, "id", f"{w}.final", out), _str(f, "category", f"{w}.final", out), _str(f, "text", f"{w}.final", out),
                                  tuple(ch), _str(f, "answer", f"{w}.final", out), _str(f, "explanation", f"{w}.final", out))
        mp = s.get("musicPosition")
        if type(mp) is not int:
            out.append(f"{w}.musicPosition: must be an integer 1..4")
            mp = 0
        if final is not None:
            sets.append(QuestionSet(str(s.get("id")), tuple(ox), tuple(bz), final, mp))
    for ti, t in enumerate(data.get("tracks") or []):
        w = f"tracks[{ti}]"
        if not _shape(t, TRACK_KEYS, TRACK_REQUIRED, w, out):
            continue
        w = f"track {t.get('key', ti)}"
        c = t.get("credit")
        credit = Credit("", "")
        if _shape(c, CREDIT_KEYS, {"title", "license"}, f"{w}.credit", out):
            credit = Credit(_str(c, "title", f"{w}.credit", out), _str(c, "license", f"{w}.credit", out),
                            _str(c, "author", f"{w}.credit", out, True), _str(c, "performer", f"{w}.credit", out, True),
                            _str(c, "source", f"{w}.credit", out, True))
        file = _str(t, "file", w, out)
        path = media_dir / file if file else None
        if path is not None and (".." in Path(file).parts or Path(file).is_absolute() or not path.is_file()):
            out.append(f"{w}.file: {file!r} is not a file under {media_dir.name}/")
            size = 1
        else:
            size = path.stat().st_size if path else 1
        dur = t.get("durationSec")
        if not isinstance(dur, (int, float)) or isinstance(dur, bool) or dur <= 0:
            out.append(f"{w}.durationSec: must be a positive number")
            dur = 1.0
        clips = []
        for i, cl in enumerate(t.get("clips") or []):
            if isinstance(cl, list) and len(cl) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in cl):
                clips.append((float(cl[0]), float(cl[1])))
            else:
                out.append(f"{w}.clips[{i}]: must be [startSec, endSec]")
        tracks.append(MusicTrack(
            key=_str(t, "key", w, out), asset_id=str(t.get("assetId", "")), bytes=size, duration_sec=float(dur),
            answer=_str(t, "answer", w, out), aliases=_strs(t, "aliases", w, out), explanation=_str(t, "explanation", w, out),
            clips=tuple(clips), clues=_strs(t, "clues", w, out), credit=credit,
            category=t.get("category", "Midnight Concert"), text=t.get("text", "What's the title of this piece?"), file=file))
    hard = [e for e in out if ".file:" not in e]  # a missing media file does not stop the other checks
    return (ContentBank(tuple(sets), tuple(tracks)) if not hard else None), out


def extra_checks(bank: ContentBank) -> tuple[list[str], list[str]]:
    """Alias checks beyond model.validate_bank. Returns (errors, warnings)."""
    errors, warnings = [], []
    owners: dict[str, str] = {}

    def check(where, answer, aliases):
        seen = {normalize(answer)}
        for a in aliases:
            n = normalize(a)
            if not n:
                errors.append(f"{where}: alias {a!r} has no letters or digits")
            elif n in seen and n != normalize(answer):
                errors.append(f"{where}: alias {a!r} appears twice")
            seen.add(n)
            if HANGUL.search(a):
                warnings.append(f"{where}: alias {a!r} is not English (the game is English only)")
        for a in (answer, *aliases):
            n = normalize(a)
            other = owners.get(n)
            if n and other and other != where:
                errors.append(f"{where}: {a!r} is also an answer or alias of {other} (two questions with one answer)")
            owners.setdefault(n, where)
    for s in bank.sets:
        for q in s.buzzers:
            check(f"{s.id}/{q.id}", q.answer, q.aliases)
    for t in bank.tracks:
        check(f"track {t.key}", t.answer, t.aliases)
        if t.answer and normalize(t.answer) not in {normalize(a) for a in t.aliases}:
            warnings.append(f"track {t.key}: the title is not listed among aliases (it still matches, listing it is clearer)")
    ids = [t.asset_id for t in bank.tracks]
    if len(set(ids)) != len(ids):
        errors.append("tracks: duplicate assetId")
    return errors, warnings


def check_bank_file(path: Path, media_dir: Path) -> tuple[ContentBank | None, list[str], list[str]]:
    """(bank or None, errors, warnings)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"{path}: file not found"], []
    except ValueError as e:
        return None, [f"{path}: not valid JSON ({e})"], []
    bank, errors = parse_bank(data, media_dir)
    warnings: list[str] = []
    if bank is None:
        return None, errors, warnings
    errors += validate_bank(bank)
    e2, w2 = extra_checks(bank)
    errors += e2
    warnings += w2
    return (bank if not errors else None), errors, warnings


def load_bank(path: Path, media_dir: Path) -> ContentBank:
    bank, errors, _ = check_bank_file(path, media_dir)
    if errors or bank is None:
        raise BankError(errors)
    return bank


def bank_to_dict(bank: ContentBank) -> dict:
    """The inverse of parse_bank (used to write the dev bank and by tests)."""
    def credit(c):
        d = {"title": c.title, "license": c.license}
        for k in ("author", "performer", "source"):
            if getattr(c, k):
                d[k] = getattr(c, k)
        return d
    return {
        "format": FORMAT,
        "sets": [{"id": s.id, "musicPosition": s.music_position,
                  "ox": [{"id": q.id, "category": q.category, "text": q.text, "answer": q.answer, "explanation": q.explanation} for q in s.ox],
                  "buzzers": [{"id": q.id, "category": q.category, "text": q.text, "answer": q.answer, "aliases": list(q.aliases),
                               "explanation": q.explanation} for q in s.buzzers],
                  "final": {"id": s.final.id, "category": s.final.category, "text": s.final.text, "choices": list(s.final.choices),
                            "answer": s.final.answer, "explanation": s.final.explanation}} for s in bank.sets],
        "tracks": [{"key": t.key, "assetId": t.asset_id, "file": t.file, "durationSec": t.duration_sec, "category": t.category,
                    "text": t.text, "answer": t.answer, "aliases": list(t.aliases), "explanation": t.explanation,
                    "clips": [list(c) for c in t.clips], "clues": list(t.clues), "credit": credit(t.credit)} for t in bank.tracks],
    }
