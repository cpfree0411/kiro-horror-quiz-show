"""Question bank files: loading, the validator command, and clear errors for broken files."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from khqs.content import bank_io
from khqs.content.bank_io import BankError, bank_to_dict, check_bank_file, load_bank
from khqs.content.dev_bank import DEV_BANK_PATH, build_dev_bank
from khqs.content.model import validate_bank
from khqs.server.settings import REPO, Settings

MEDIA = REPO / "media"


def good():
    return json.loads(DEV_BANK_PATH.read_text(encoding="utf-8"))


def write(tmp_path, data, name="bank.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def errors_for(tmp_path, mutate):
    d = good()
    mutate(d)
    _, errors, _ = check_bank_file(write(tmp_path, d), MEDIA)
    return "\n".join(errors)


def test_dev_bank_file_loads_is_valid_and_round_trips():
    bank = build_dev_bank(MEDIA)
    assert validate_bank(bank) == []
    assert [s.id for s in bank.sets] == ["dev-a", "dev-b"] and len(bank.tracks) == 3
    assert all(t.file and t.bytes > 400_000 for t in bank.tracks)
    again = bank_io.parse_bank(bank_to_dict(bank), MEDIA)[0]
    assert again == bank
    _, errors, warnings = check_bank_file(DEV_BANK_PATH, MEDIA)
    assert errors == [] and warnings == []  # English-only aliases, titles listed


def test_every_field_the_engine_needs_is_in_the_file_format():
    d = good()
    assert set(d) == {"format", "sets", "tracks"}
    assert set(d["sets"][0]) == {"id", "musicPosition", "ox", "buzzers", "final"}
    assert set(d["tracks"][0]) >= {"assetId", "file", "durationSec", "answer", "aliases", "explanation", "clips", "clues", "composer", "credit"}
    game = load_bank(DEV_BANK_PATH, MEDIA).select(0, __import__("random").Random(1))
    assert len(game.questions) == 8 and game.track.clips and len(game.track.clues) == 2


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d.update(format="x"), "bank.format"),
    (lambda d: d.update(extra=1), "unknown field 'extra'"),
    (lambda d: d["sets"][0]["ox"][0].update(answer="Y"), "OX answer must be O or X"),
    (lambda d: d["sets"][0]["ox"][0].update(category="C" * 30), "category length"),
    (lambda d: d["sets"][0]["ox"][0].update(text="t" * 200), "text length"),
    (lambda d: d["sets"][0]["ox"][0].pop("explanation"), "missing field 'explanation'"),
    (lambda d: d["sets"][0]["buzzers"][0].update(category="Mirror Room"), "appears in the category or text"),
    (lambda d: d["sets"][0]["buzzers"][0].update(aliases=["The mirror", "the  MIRROR!"]), "appears twice"),
    (lambda d: d["sets"][0]["buzzers"][1].update(answer="Mirror"), "two questions with one answer"),
    (lambda d: d["sets"][0]["buzzers"][0].update(aliases=["!!!"]), "no letters or digits"),
    (lambda d: d["sets"][0]["buzzers"].pop(), "needs 3 regular buzzer questions"),
    (lambda d: d["sets"][0]["final"].update(choices=["a", "a", "b", "c"]), "4 distinct choices"),
    (lambda d: d["sets"][0]["final"].update(answer="E"), "final answer must be A..D"),
    (lambda d: d["sets"][0].update(musicPosition=9), "music_position must be 1..4"),
    (lambda d: d["tracks"][0].update(assetId="a-xyz"), "asset id must match"),
    (lambda d: d["tracks"][0].update(file="nope.mp3"), "is not a file under media/"),
    (lambda d: d["tracks"][0].update(file="../MANIFEST.sha256"), "is not a file under media/"),
    (lambda d: d["tracks"][0].update(clips=[[0, 9], [0, 5], [0, 30]]), "must get longer"),
    (lambda d: d["tracks"][0].update(clips=[[0, 9], [0, 12], [0, 99]]), "outside 0..30.0"),
    (lambda d: d["tracks"][0].update(clues=["only one"]), "needs 2 clues"),
    (lambda d: d["tracks"][0].update(clues=["It is Danse Macabre!", "x"]), "a clue contains the title"),
    (lambda d: d["tracks"][0].update(category="Danse Macabre Night"), "appears in the category or text"),
    (lambda d: d["tracks"][0].pop("composer"), "missing field 'composer'"),
    (lambda d: d["tracks"][0].update(composer=""), "composer: must be a non-empty string"),
    (lambda d: d["tracks"][0].update(composer="   "), "composer: must be a non-empty string"),
    (lambda d: d["tracks"][0].update(composer=7), "composer: must be a non-empty string"),
    (lambda d: d["tracks"][0].update(clues=["By Camille Saint-Saëns, of course.", "x"]), "a clue contains the composer"),
    (lambda d: d["tracks"][0].update(text="A piece by Camille Saint-Saëns?"), "the composer ('Camille Saint-Saëns') appears in the category or text"),
    (lambda d: d["tracks"][0]["credit"].pop("license"), "missing field 'license'"),
    (lambda d: d["tracks"][1].update(assetId=d["tracks"][0]["assetId"]), "duplicate assetId"),
    (lambda d: d["sets"][1]["ox"][0].update(id=d["sets"][0]["ox"][0]["id"]), "duplicate question id"),
])
def test_broken_banks_give_clear_errors(tmp_path, mutate, needle):
    assert needle in errors_for(tmp_path, mutate)


def test_non_english_aliases_warn_but_do_not_fail(tmp_path):
    d = good()
    d["sets"][0]["buzzers"][0]["aliases"].append("거울")
    bank, errors, warnings = check_bank_file(write(tmp_path, d), MEDIA)
    assert bank is not None and errors == [] and any("not English" in w for w in warnings)


def test_missing_and_malformed_files(tmp_path):
    assert "file not found" in check_bank_file(tmp_path / "none.json", MEDIA)[1][0]
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert "not valid JSON" in check_bank_file(bad, MEDIA)[1][0]
    with pytest.raises(BankError):
        load_bank(bad, MEDIA)


def run_cli(*args):
    return subprocess.run([sys.executable, "-B", "-m", "khqs.content.check", *map(str, args)], capture_output=True, text=True,
                          env={"PYTHONPATH": str(REPO / "server"), "PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})


def test_validator_command_ok_and_failing(tmp_path):
    ok = run_cli(DEV_BANK_PATH)
    assert ok.returncode == 0 and ok.stdout.startswith("OK:") and "2 sets, 3 tracks" in ok.stdout
    d = good()
    d["sets"][0]["buzzers"][0]["category"] = "Mirror Room"
    d["tracks"][0]["file"] = "gone.mp3"
    bad = run_cli(write(tmp_path, d))
    assert bad.returncode == 1
    assert "ERROR   dev-a/q-bz-01: the answer or an alias ('Mirror') appears in the category or text" in bad.stdout
    assert "gone.mp3" in bad.stdout and "is NOT usable" in bad.stdout


def test_the_composer_is_a_required_private_string_on_every_track_and_round_trips():
    bank = load_bank(DEV_BANK_PATH, MEDIA)
    assert {t.key: t.composer for t in bank.tracks} == {"dm": "Camille Saint-Saëns", "hk": "Edvard Grieg", "tf": "Johann Sebastian Bach"}
    assert [t.composer for t in bank.tracks] == [d["composer"] for d in bank_to_dict(bank)["tracks"]]
    t = bank.tracks[0]
    assert t.hints == (("clue", t.clues[0]), ("clue", t.clues[1]), ("composer", "Camille Saint-Saëns"))  # the spoken order
