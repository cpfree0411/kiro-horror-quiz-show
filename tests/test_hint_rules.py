"""P7: the local phrase lists for 'give me a hint' and for the others' yes or no."""
import pytest

from khqs.rules import hints as h

ANSWER, ALIASES = "Danse Macabre", ["Dance Macabre", "Danse Macabre Op 40"]


@pytest.mark.parametrize("heard", [
    "hint", "Hint!", "a hint", "give me a hint", "Give me a hint, please", "I need a hint", "clue", "can I have a clue",
    "help", "help me", "it's too hard", "it is too hard, give me a hint", "too difficult", "this is so hard", "I give up",
    "HINT PLEASE", "any hints?", "Can you give us a clue?",
])
def test_hint_requests(heard):
    assert h.is_hint_request(heard, ANSWER, ALIASES)


@pytest.mark.parametrize("heard", [
    "", "   ", "Danse Macabre", "Moonlight Sonata", "hello", "I think it is Mozart", "the hinterlands", "chintz", "helpful", "no idea",
    "a clueless guess",
])
def test_ordinary_words_are_not_hint_requests(heard):
    assert not h.is_hint_request(heard, ANSWER, ALIASES)


@pytest.mark.parametrize("heard", [
    "Danse Macabre", "no hint needed, it's Danse Macabre", "hint: Danse Macabre", "Dance Macabre, give me no clue", "danse macabre help",
    "is it Danse Macabre? too hard",
])
def test_an_answer_that_also_says_hint_is_an_answer(heard):
    assert h.looks_like_hint_request(heard) or "hint" not in heard.lower()  # the words are there ...
    assert not h.is_hint_request(heard, ANSWER, ALIASES)  # ... and the answer still wins


def test_the_answer_rule_uses_the_judge_so_a_close_slip_is_still_an_answer():
    assert not h.is_hint_request("hint dance macabre", ANSWER, ALIASES)
    assert not h.is_hint_request("hint danse macab", ANSWER, ALIASES)  # fuzzy music matching, as in the judge
    assert h.is_hint_request("hint moonlight", ANSWER, ALIASES)


def test_a_non_string_is_never_a_request():
    assert not h.is_hint_request(None, ANSWER) and not h.is_hint_request(7, ANSWER)


@pytest.mark.parametrize("heard", [
    "yes", "Yes!", "yeah", "yep", "sure", "okay", "OK", "fine", "go ahead", "Go ahead!", "alright", "all right", "of course",
    "why not", "I agree", "sounds good", "no problem", "no worries", "I don't mind", "I do not mind", "yes, go ahead",
])
def test_agree(heard):
    assert h.classify_consent(heard) == h.AGREE


@pytest.mark.parametrize("heard", [
    "no", "No!", "nope", "nah", "never", "no way", "NO WAY", "not really", "absolutely not", "I don't agree", "I disagree", "no thanks",
    "yes... no", "sure, no way", "okay never", "I don't think so", "don't give it to him",
])
def test_refuse_and_any_refusal_refuses(heard):
    assert h.classify_consent(heard) == h.REFUSE


@pytest.mark.parametrize("heard", ["", "  ", "mmm", "what?", "hmm maybe", "let me think", "banana", "I don't know", "I don't know what he said", None, 5])
def test_unclear_changes_nothing(heard):
    assert h.classify_consent(heard) == h.UNCLEAR
