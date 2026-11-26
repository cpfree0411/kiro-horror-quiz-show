"""P4: the English show bank (banks/en-bank.json) is valid, plays whole games cleanly and accepts spoken forms."""
from pathlib import Path

import pytest

from khqs.content.bank_io import check_bank_file, load_bank
from khqs.rules.judge import answer_matches
from support.harness import new_sim
from support.randbots import random_bots
from support.secrecy import assert_no_leaks

REPO = Path(__file__).resolve().parents[1]
BANK_FILE = REPO / "banks" / "en-bank.json"
MEDIA = REPO / "media"
BANK = load_bank(BANK_FILE, MEDIA)
NAMES = {1: ("Mina",), 2: ("Mina", "Junho"), 3: ("Mina", "Junho", "Ray")}


def test_bank_file_has_no_errors_or_warnings():
    bank, errors, warnings = check_bank_file(BANK_FILE, MEDIA)
    assert bank is not None and errors == [] and warnings == []
    assert len(bank.sets) == 2 and len(bank.tracks) == 3


@pytest.mark.parametrize("players,seed,game_index", [(1, 31, 0), (2, 32, 1), (3, 33, 0), (3, 34, 1), (2, 35, 0), (1, 36, 1)])
def test_random_full_games_on_the_english_bank_are_clean(players, seed, game_index):
    sim = new_sim(BANK, names=NAMES[players], seed=seed, game_index=game_index)
    random_bots(sim, seed)
    sim.until_ended()
    assert sim.stream[-1]["type"] == "game.ended"
    assert len(sim.of("answer.revealed")) == 8
    assert_no_leaks(sim)


def _buzzer(answer):
    return next(q for s in BANK.sets for q in s.buzzers if q.answer == answer)


SPOKEN = {
    "Mummy": (["mummy", "a mummy", "Mummy!", "the mummies"], ["zombie"]),
    "Coffin": (["coffin", "a coffin", "casket"], ["bed", "box"]),
    "Trick or treat": (["trick or treat", "Trick or treat!", "trick-or-treat"], ["happy halloween"]),
    "Eight": (["eight", "8", "eight legs", "8 legs"], ["six"]),
    "Full moon": (["full moon", "the full moon", "moon", "a full moon"], ["the sun"]),
    "Skeleton": (["skeleton", "a skeleton", "skeletons"], ["ghost"]),
}


@pytest.mark.parametrize("answer", sorted(SPOKEN))
def test_spoken_buzzer_forms(answer):
    q, (ok, no) = _buzzer(answer), SPOKEN[answer]
    for heard in ok:
        assert answer_matches(heard, q.answer, q.aliases, "buzzer"), heard
    for heard in no:
        assert not answer_matches(heard, q.answer, q.aliases, "buzzer"), heard


@pytest.mark.parametrize("key,heard", [("dm", "dance macabre"), ("dm", "danse macabre by saint-saens"),
                                       ("hk", "hall of the mountain king"), ("hk", "mountain king"),
                                       ("tf", "toccata and fugue"), ("tf", "bach toccata")])
def test_spoken_music_titles(key, heard):
    t = next(t for t in BANK.tracks if t.key == key)
    assert answer_matches(heard, t.answer, t.aliases, "av")


def test_act2_answer_cards_stay_short():
    """Act-2 explanations are drawn as the big answer card on the stage; long lines overflow it."""
    for s in BANK.sets:
        for q in s.buzzers:
            assert len(q.explanation) <= 30, q.id
    for t in BANK.tracks:
        assert len(t.explanation) <= 32, t.key


def test_every_english_track_has_its_composer_and_no_hint_leaks_it_early():
    assert {t.key: t.composer for t in BANK.tracks} == {
        "dm": "Camille Saint-Saëns", "hk": "Edvard Grieg", "tf": "Johann Sebastian Bach"}
    for t in BANK.tracks:
        assert t.composer == t.credit.author  # the credit and the third spoken hint agree
        assert all(t.composer.casefold() not in c.casefold() for c in t.clues)
        assert t.composer.casefold() not in f"{t.category} {t.text}".casefold()
