import dataclasses
import random

from khqs.content.model import ContentBank, validate_bank
from support.content_fixture import BANK, SET_A, SET_B, TRACKS


def test_fixture_bank_is_valid():
    assert validate_bank(BANK) == []


def test_select_builds_eight_questions_in_show_order():
    g = BANK.select(0, random.Random(1))
    assert [q.number for q in g.questions] == list(range(1, 9))
    assert [q.kind for q in g.questions] == ["ox", "ox", "ox", "buzzer", "av", "buzzer", "buzzer", "final"]
    assert [q.act for q in g.questions] == [1, 1, 1, 2, 2, 2, 2, 3]
    assert [q.index_in_act for q in g.questions] == [1, 2, 3, 1, 2, 3, 4, 1]
    assert sum(q.kind == "av" for q in g.questions) == 1
    av = g.questions[4]
    assert av.track is g.track and av.id == "q-av-05"


def test_sets_alternate_and_music_position_follows_the_set():
    assert BANK.select(0, random.Random(1)).set_id == "set-a"
    assert BANK.select(1, random.Random(1)).set_id == "set-b"
    assert BANK.select(2, random.Random(1)).set_id == "set-a"
    assert BANK.select(1, random.Random(1)).questions[5].kind == "av"  # position 3 of act 2


def test_track_choice_is_seeded_and_covers_all_tracks():
    assert BANK.select(0, random.Random(5)).track == BANK.select(0, random.Random(5)).track
    assert {BANK.select(0, random.Random(s)).track.key for s in range(30)} == {t.key for t in TRACKS}


def test_validation_catches_problems():
    bad_ox = dataclasses.replace(SET_A.ox[0], answer="Y", category="C" * 23, text="t" * 111)
    bad = dataclasses.replace(SET_A, ox=(bad_ox, *SET_A.ox[1:]), music_position=5)
    bad_track = dataclasses.replace(TRACKS[0], asset_id="a-xyz", clues=("The Danse Macabre!", "x"), clips=((0, 10), (0, 5), (0, 30)))
    problems = validate_bank(ContentBank(sets=(bad, SET_B), tracks=(bad_track,)))
    text = "\n".join(problems)
    for needle in ("OX answer must be O or X", "category length", "text length", "music_position", "asset id", "a clue contains the title", "longer"):
        assert needle in text, needle


def test_validation_flags_an_answer_hiding_in_the_category_or_text():
    leaky = dataclasses.replace(SET_A.buzzers[1], category="Pumpkin Patch")
    leaky2 = dataclasses.replace(SET_A.buzzers[0], text="Which mirror is it?")
    bad = dataclasses.replace(SET_A, buzzers=(leaky2, leaky, SET_A.buzzers[2]))
    text = "\n".join(validate_bank(ContentBank(sets=(bad, SET_B), tracks=TRACKS)))
    assert text.count("appears in the category or text") == 2
    leaky_track = dataclasses.replace(TRACKS[0], category="Danse Macabre Night")
    assert "appears in the category or text" in "\n".join(validate_bank(ContentBank(sets=(SET_A, SET_B), tracks=(leaky_track,))))
