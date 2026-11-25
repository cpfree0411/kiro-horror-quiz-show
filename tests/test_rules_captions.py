from khqs.rules.captions import CaptionFilter, CaptionSecrets

S = CaptionSecrets(phrases=("Danse Macabre", "죽음의 무도", "Saint-Saëns, Danse Macabre"))


def run(chunks, secrets=S, final_last=True):
    f = CaptionFilter()
    sent = []
    for i, c in enumerate(chunks):
        r = f.process("u-1", c, final_last and i == len(chunks) - 1, secrets)
        if r is not None:
            sent.append(r)
    return sent


def test_safe_text_passes_cumulatively_by_whole_words():
    sent = run(["Welcome", "Welcome to the", "Welcome to the show tonight!"])
    assert sent == ["Welcome to the show tonight!"] or sent[-1] == "Welcome to the show tonight!"
    assert all(s == s.strip() for s in sent)


def test_partial_trailing_word_is_held_back():
    f = CaptionFilter()
    assert f.process("u-1", "Welcome to the sho", False, CaptionSecrets()) == "Welcome to the"


def test_answer_blocks_whole_utterance_and_nothing_more_is_sent():
    f = CaptionFilter()
    assert f.process("u-1", "Let me think about it,", False, S) == "Let me think about it,"
    assert f.process("u-1", "Let me think about it, it is Danse Macabre", False, S) is None
    assert f.process("u-1", "Let me think about it, it is Danse Macabre by Saint-Saens", True, S) is None
    # a different utterance is unaffected
    assert f.process("u-2", "Next question!", True, S) == "Next question!"


def test_leading_words_of_a_multiword_secret_are_held():
    f = CaptionFilter()
    assert f.process("u-1", "I believe the piece is Danse ", False, S) == "I believe the piece is"
    assert f.process("u-1", "I believe the piece is Danse Macabre", False, S) is None


def test_korean_alias_and_explanation_are_blocked():
    assert run(["그건 죽음의 무도 입니다"]) == []
    s = CaptionSecrets(phrases=("Spiders have eight legs, so they are arachnids.",))
    assert run(["Spiders have eight legs so they are arachnids"], s) == []


def test_substring_inside_longer_word_is_blocked_conservatively():
    s = CaptionSecrets(phrases=("Mirror",))
    assert run(["Never look into mirrors"], s) == []


def test_block_all_for_buzzer_reading():
    assert run(["At midnight, what should you never look into?"], CaptionSecrets(block_all=True)) == []


def test_one_letter_assertions_blocked_for_both_ox_options():
    ox = CaptionSecrets(letter_kind="ox")
    for t in ["The answer is O!", "The correct answer is oh", "the answer is ex", "Correct, it's X", "That is true!", "It's false"]:
        assert run([t], ox) == [], t
    for t in ["Is this true or false?", "Get your paddles ready!", "O or X, you decide"]:
        assert run([t], ox) != [], t


def test_one_letter_assertions_for_final():
    fin = CaptionSecrets(letter_kind="letters")
    assert run(["The correct answer is B!"], fin) == []
    assert run(["And the answer is, ay"], fin) == []
    assert run(["A, the monster. B, the scientist. C, the village. D, the detective."], fin) != []


def test_long_text_is_cut_to_300():
    out = run(["word " * 100], CaptionSecrets())
    assert out and len(out[-1]) <= 300
