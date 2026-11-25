import pytest

from khqs.rules.judge import answer_matches, normalize


def test_normalize_strips_case_space_punctuation_nfkc():
    assert normalize("  Danse   Macabre! ") == "dansemacabre"
    assert normalize("Saint-Saëns") == "saintsaëns"
    assert normalize("ＭＩＲＲＯＲ") == "mirror"  # full-width -> NFKC
    assert normalize("토카타, 푸가!") == "토카타푸가"
    assert normalize("...") == ""


@pytest.mark.parametrize("heard", ["Mirror", "  mirror ", "MIRROR.", "mir-ror"])
def test_exact_after_normalisation(heard):
    assert answer_matches(heard, "Mirror", ["The mirror"], "buzzer")


def test_alias_english_and_korean():
    assert answer_matches("거울", "Mirror", ["거울", "the mirror"], "buzzer")
    assert answer_matches("The Mirror", "Mirror", ["the mirror"], "buzzer")


def test_regular_questions_are_exact_only():
    assert not answer_matches("a mirror on the wall", "Mirror", [], "buzzer")
    assert not answer_matches("a mirror on the wall", "Mirror", [], "final")
    assert not answer_matches("mirro", "Mirror", [], "buzzer")
    assert not answer_matches("", "Mirror", [], "buzzer")
    assert not answer_matches("!!!", "Mirror", [], "buzzer")


def test_music_title_alone_is_enough():
    aliases = ["Danse Macabre", "죽음의 무도"]
    assert answer_matches("Danse Macabre", "Danse Macabre", aliases, "av")
    assert answer_matches("Saint-Saëns Danse Macabre", "Danse Macabre", aliases, "av")
    assert answer_matches("I think it is danse macabre by somebody", "Danse Macabre", aliases, "av")
    assert answer_matches("죽음의 무도입니다", "Danse Macabre", aliases, "av")


def test_music_allows_a_small_slip():
    aliases = ["Danse Macabre"]
    assert answer_matches("dance macabre", "Danse Macabre", aliases, "av")
    assert answer_matches("danse makabre", "Danse Macabre", aliases, "av")
    assert answer_matches("Hall of the Mountain Kin", "In the Hall of the Mountain King", ["Hall of the Mountain King"], "av")
    assert answer_matches("죽음에 무도", "Danse Macabre", ["죽음의 무도"], "av")  # one syllable slip: ratio exactly 0.8


def test_music_rejects_wrong_titles():
    aliases = ["Danse Macabre", "죽음의 무도"]
    for wrong in ["Moonlight Sonata", "Flight of the Bumblebee", "Toccata and Fugue", "danse", "macabre", "무도회"]:
        assert not answer_matches(wrong, "Danse Macabre", aliases, "av"), wrong


def test_short_keys_do_not_trigger_music_substring_rule():
    assert not answer_matches("a banana", "Ox", ["Ox"], "av")  # key length 2 < 3
    assert answer_matches("ox", "Ox", [], "av")  # but exact still works


def test_composer_not_required_and_not_sufficient_alone():
    assert not answer_matches("Saint-Saëns", "Danse Macabre", ["Danse Macabre"], "av")
