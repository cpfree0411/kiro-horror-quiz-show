"""P7: spoken hints on request in the music question (engine level, scripted players, fake clock, fake MC)."""
import random

import pytest

from khqs.engine.effects import McSay
from khqs.engine.rounds import BuzzRound
from support.bots import Bots
from support.content_fixture import BANK, TRACKS
from support.harness import new_sim
from support.randbots import random_bots
from support.secrecy import assert_no_leaks
from support.seeds import seed_for_track

CLUE1, CLUE2 = TRACKS[0].clues
COMPOSER = TRACKS[0].composer
NAMES3 = ("Mina", "Junho", "Ray")


def music_sim(names=NAMES3, **kw):
    """A game paused at the first music clip (level 0). The fake stage plays and ends each clip by itself."""
    sim = new_sim(BANK, names=names, seed=seed_for_track("dm"), **kw)
    Bots(sim, ox=lambda s, n: "O" if s == 0 else "X")
    sim.until_type("av.play")
    return sim


def at_level(sim, level, during_music=True):
    """Let the ladder run (nobody buzzes) until `level`, stopping while that clip plays or right after it ended."""
    want = ("buzzer.media",) if during_music else ("buzzer.open",)
    sim.run_until(lambda: sim.eng.hint_level == level and sim.eng.phase in want and sim.eng.round.holder is None,
                  what=f"level {level}")


def hold(sim, seat):
    assert sim.act(seat, {"type": "buzz"}).ok
    sim.until_phase("buzzer.answering")
    assert sim.eng.round.holder == seat


def say(sim, seat, text, rec="clear", voiced=True):
    l = sim.last_listen("answer")
    assert l is not None and l.seat == seat
    assert sim.eng.mc_voice_answer(l.listen_id, text, rec, voiced)
    sim.pump()


def vote_says(sim, text, rec="clear", voiced=True):
    l = sim.last_listen("consent")
    assert l is not None
    ok = sim.eng.mc_voice_consent(l.listen_id, text, rec, voiced)
    sim.pump()
    return ok


def vote(sim, seat, agree):
    return sim.act(seat, {"type": "hint_vote", "agree": agree})


def cues(sim, *names):
    return [(e.cue, e.facts) for _, e, _ in sim.mc_fx if isinstance(e, McSay) and (not names or e.cue in names)]


def grants(sim):
    return [f for c, f in cues(sim, "hint_grant")]


def phases_since(sim, sseq):
    return [m["data"]["phase"] for m in sim.stream if m["type"] == "phase.changed" and m["sseq"] > sseq]


def finish(sim):
    sim.until_type("score.settled", 5)
    rev = [m for m in sim.of("answer.revealed") if m["data"]["questionId"] == "q-av-05"][0]
    settled = [m for m in sim.of("score.settled") if m["sseq"] > rev["sseq"]][0]
    return {d["seat"]: d["delta"] for d in settled["data"]["deltas"]}


# ---------------------------------------------------------------- a request at each level, during and after the music
@pytest.mark.parametrize("level,during_music", [(0, True), (0, False), (1, True), (1, False), (2, True), (2, False)])
def test_a_voice_request_at_each_level_asks_the_others_then_grants_clue_one_and_the_requester_answers(level, during_music):
    sim = music_sim()
    if level or not during_music:
        at_level(sim, level, during_music)
    if level == 0 and not during_music:
        sim.run_until(lambda: sim.eng.phase == "buzzer.open", what="open window")
    hold(sim, 0)
    interrupted = sim.of("buzzer.pressed")[-1]["data"]["mediaInterrupted"]
    assert interrupted is during_music
    before = sim.eng._sseq
    say(sim, 0, "it's too hard, give me a hint")
    assert sim.eng.phase == "buzzer.hint"  # the stage shows its HINT! board; the MC and the phones carry the rest
    assert not sim.of("buzzer.judged") and sim.eng.round.attempts == [] and sim.eng.round.locked == []
    assert cues(sim, "hint_ask") == [("hint_ask", {"name": "Mina"})]
    sim.run(800)  # the MC finishes the question, then the consent window opens for the other two
    assert sim.last_listen("consent").seat == 0 and sim.last_listen("consent").purpose == "consent"
    assert [sim.eng.phone_view(s)["screen"] for s in (0, 1, 2)] == ["hint_wait", "hint_vote", "hint_vote"]
    assert sim.eng.phone_view(1)["own"]["hint"]["requester"] == "Mina"
    assert vote(sim, 1, True).ok and sim.eng.phase == "buzzer.hint"  # one yes of two: still waiting
    assert [sim.eng.phone_view(s)["screen"] for s in (1, 2)] == ["hint_voted", "hint_vote"]
    assert vote(sim, 2, True).ok
    assert grants(sim) == [{"name": "Mina", "how": "agreed", "kind": "clue", "text": CLUE1, "number": 1}]
    sim.until_phase("buzzer.answering")
    assert phases_since(sim, before)[:2] == ["buzzer.hint", "buzzer.answering"]
    assert sim.eng.round.holder == 0 and sim.eng.round.hints_given == 1 and sim.eng.round.attempts == []
    say(sim, 0, "Danse Macabre")  # the requester answers at once, still holding the buzzer
    assert sim.of("buzzer.judged")[-1]["data"] == {"seat": 0, "correct": True, "lockedOut": []}
    assert finish(sim) == {0: 20, 1: 0, 2: 0}


def test_the_stage_stream_only_shows_the_hint_phase_and_no_new_message_types():
    sim = music_sim()
    hold(sim, 1)
    start = len(sim.stream)
    say(sim, 1, "hint")
    sim.run(800)
    vote(sim, 0, True), vote(sim, 2, True)
    sim.until_phase("buzzer.answering")
    new = [m["type"] for m in sim.stream[start:]]
    assert set(new) <= {"phase.changed", "mc.status"}  # nothing about the request, the votes or the hint is on the wire
    assert [m["data"]["phase"] for m in sim.stream[start:] if m["type"] == "phase.changed"] == ["buzzer.hint", "buzzer.answering"]
    assert "fiddle" not in repr(sim.stream[start:]) and COMPOSER not in repr(sim.stream)


def test_a_wrong_answer_after_the_hint_locks_the_requester_out_and_the_round_goes_on_for_the_others():
    sim = music_sim()
    hold(sim, 0)
    say(sim, 0, "give me a clue")
    sim.run(800)
    vote(sim, 1, True), vote(sim, 2, True)
    sim.until_phase("buzzer.answering")
    say(sim, 0, "Moonlight Sonata")
    j = sim.of("buzzer.judged")[-1]["data"]
    assert j == {"seat": 0, "correct": False, "lockedOut": [0]}
    sim.run_until(lambda: sim.eng.phase in ("buzzer.open", "buzzer.media") and sim.eng.round.armed, what="buzzers reopen")
    assert sim.act(0, {"type": "buzz"}).error == "locked_out"
    hold(sim, 1)  # the others carry on at the same level
    say(sim, 1, "Danse Macabre")
    assert finish(sim) == {0: 0, 1: 20, 2: 0}


def test_everyone_wrong_after_hints_still_continues_the_automatic_ladder_with_a_longer_listen():
    sim = music_sim()
    hold(sim, 0)
    say(sim, 0, "hint")
    sim.run(800)
    vote(sim, 1, True), vote(sim, 2, True)
    sim.until_phase("buzzer.answering")
    say(sim, 0, "nope")
    for seat in (1, 2):
        sim.run_until(lambda: sim.eng.round.armed and sim.eng.round.holder is None, what="buzzers open")
        hold(sim, seat)
        say(sim, seat, "nope")
    sim.until_type("av.hint")
    assert sim.of("av.hint")[0]["data"]["level"] == 1
    sim.run_until(lambda: cues(sim, "longer_listen"), what="the MC line after the gate ack")
    assert cues(sim, "longer_listen") == [("longer_listen", {"level": 1, "max_level": 2})]
    assert sim.eng.round.hints_given == 1 and sim.eng.round.hint_asked == {0}  # the ladder does not reset the limits


# ---------------------------------------------------------------- consent
def ask(sim, seat, text="give me a hint"):
    hold(sim, seat)
    say(sim, seat, text)
    sim.run(800)  # hint_ask has been said; the window is open


def test_consent_refused_by_a_phone_no_ends_the_window_at_once_and_the_requester_must_answer_without_a_hint():
    sim = music_sim()
    ask(sim, 0)
    t = sim.clock.now_ms()
    assert vote(sim, 2, False).ok
    assert cues(sim, "hint_refused") == [("hint_refused", {"name": "Mina"})] and grants(sim) == []
    assert sim.clock.now_ms() - t == 0  # a refusal does not wait for the others
    sim.until_phase("buzzer.answering")
    assert sim.eng.round.holder == 0 and sim.eng.round.hints_given == 0 and sim.eng.round.hint_asked == {0}
    say(sim, 0, "Danse Macabre")  # still a normal answer window with the normal rules
    assert sim.of("buzzer.judged")[-1]["data"]["correct"] is True


def test_a_refused_requester_who_answers_wrong_is_locked_out_as_usual():
    sim = music_sim()
    ask(sim, 0)
    vote(sim, 1, False)
    sim.until_phase("buzzer.answering")
    say(sim, 0, "Moonlight Sonata")
    assert sim.of("buzzer.judged")[-1]["data"] == {"seat": 0, "correct": False, "lockedOut": [0]}


def test_a_refusal_wins_over_agreement_even_when_the_yes_came_first():
    sim = music_sim()
    ask(sim, 0)
    vote(sim, 1, True)
    assert grants(sim) == []
    vote(sim, 2, False)
    assert grants(sim) == [] and cues(sim, "hint_refused")


def test_spoken_votes_agree_waits_for_every_voter_then_grants():
    sim = music_sim()
    ask(sim, 0)
    t0 = sim.clock.now_ms()
    assert vote_says(sim, "sure")
    assert grants(sim) == []  # one voice of two voters
    assert vote_says(sim, "yeah go ahead")
    assert grants(sim)[0]["how"] == "agreed" and sim.clock.now_ms() == t0


def test_a_spoken_no_refuses_at_once_and_unclear_speech_changes_nothing():
    sim = music_sim()
    ask(sim, 0)
    assert vote_says(sim, "uhh mumble", rec="unclear")
    assert vote_says(sim, "I don't know what he said", voiced=True)  # clear but neither yes nor no
    assert vote_says(sim, "yes", voiced=False)  # no voiced evidence: ignored
    assert grants(sim) == [] and not cues(sim, "hint_refused") and sim.eng.round.consent is not None
    assert vote_says(sim, "no way")
    assert cues(sim, "hint_refused") and grants(sim) == []


def test_silence_for_the_whole_window_counts_as_yes_after_eight_seconds():
    sim = music_sim()
    ask(sim, 1)
    t0 = sim.clock.now_ms()
    sim.run_until(lambda: grants(sim), what="the grant")
    assert sim.clock.now_ms() - t0 == 8_000
    assert grants(sim) == [{"name": "Junho", "how": "silence", "kind": "clue", "text": CLUE1, "number": 1}]


def test_one_yes_and_one_silent_voter_is_granted_when_the_window_ends():
    sim = music_sim()
    ask(sim, 0)
    vote(sim, 1, True)
    t0 = sim.clock.now_ms()
    sim.run_until(lambda: grants(sim), what="the grant")
    assert sim.clock.now_ms() - t0 == 8_000 and grants(sim)[0]["how"] == "agreed"


def test_the_consent_window_opens_a_listen_for_the_room_and_closes_it():
    sim = music_sim()
    ask(sim, 0)
    l = sim.last_listen("consent")
    assert l.deadline - sim.clock.now_ms() == 8_000 and sim.eng.phone_view(1)["game"]["deadline"] == l.deadline
    vote(sim, 1, True), vote(sim, 2, True)
    assert sim.eng.round.consent is None and sim.eng.input_deadline is None
    assert not vote(sim, 1, True).ok  # a late vote is too late


def test_votes_are_validated_and_final():
    sim = music_sim()
    hold(sim, 0)
    assert vote(sim, 1, True).error == "not_now"  # no window yet
    say(sim, 0, "hint")
    sim.run(800)
    assert vote(sim, 0, True).error == "not_now"  # the requester does not vote
    assert sim.act(1, {"type": "hint_vote", "agree": "yes"}).error == "bad_input"
    assert sim.act(1, {"type": "hint_vote"}).error == "bad_input"
    assert vote(sim, 1, True).ok and vote(sim, 1, False).error == "already_answered"  # first vote is final
    assert sim.eng.round.consent.votes == {1: True}


def test_a_disconnected_player_is_not_asked_and_the_last_one_standing_is_granted_like_solo():
    sim = music_sim(names=("Mina", "Junho"))
    sim.eng.phone_connection(1, False)
    sim.pump()
    hold(sim, 0)
    say(sim, 0, "hint")
    assert cues(sim, "hint_ask") == [] and grants(sim)[0]["how"] == "solo"


def test_solo_has_nobody_to_ask_the_mc_grants_with_a_joke_and_there_is_no_window():
    sim = music_sim(names=("Mina",))
    hold(sim, 1)
    t0 = sim.clock.now_ms()
    say(sim, 1, "too hard, give me a clue")
    assert cues(sim, "hint_ask") == [] and sim.eng.round.consent is None
    assert grants(sim) == [{"name": "Mina", "how": "solo", "kind": "clue", "text": CLUE1, "number": 1}]
    assert sim.last_listen("consent") is None
    sim.until_phase("buzzer.answering")
    assert sim.clock.now_ms() - t0 == 800  # just the MC line
    say(sim, 1, "Danse Macabre")
    assert finish(sim)[1] == 20


# ---------------------------------------------------------------- the three hints and the limits
def test_the_hints_come_in_order_clue_one_clue_two_the_composer():
    sim = music_sim()
    for n, seat in enumerate((0, 1, 2), 1):
        sim.run_until(lambda: sim.eng.round.armed and sim.eng.round.holder is None, what="buzzers open")
        hold(sim, seat)
        say(sim, seat, "hint please")
        sim.run(800)
        for v in {0, 1, 2} - {seat}:
            vote(sim, v, True)
        sim.until_phase("buzzer.answering")
        assert sim.eng.round.hints_given == n
        say(sim, seat, "nope")
    assert [(g["kind"], g["text"], g["number"]) for g in grants(sim)] == [
        ("clue", CLUE1, 1), ("clue", CLUE2, 2), ("composer", COMPOSER, 3)]
    assert [g["name"] for g in grants(sim)] == ["Mina", "Junho", "Ray"]
    assert sim.eng.round.locked == [0, 1, 2]


def test_a_refused_request_gives_nothing_so_the_next_player_gets_clue_one():
    sim = music_sim()
    ask(sim, 0)
    vote(sim, 1, False)
    sim.until_phase("buzzer.answering")
    say(sim, 0, "nope")
    sim.run_until(lambda: sim.eng.round.armed and sim.eng.round.holder is None, what="buzzers open")
    ask(sim, 1)
    vote(sim, 0, True), vote(sim, 2, True)
    assert grants(sim)[0]["text"] == CLUE1 and grants(sim)[0]["number"] == 1


def test_no_hints_left_after_three_then_the_player_must_answer_and_a_second_phrase_is_just_an_answer():
    sim = music_sim()
    hold(sim, 2)
    sim.eng.round.hints_given = 3  # all three were given (only reachable with three players when every ask was granted)
    say(sim, 2, "give me a hint")
    assert cues(sim, "hint_none") == [("hint_none", {"name": "Ray", "why": "none_left"})] and grants(sim) == [] and not cues(sim, "hint_ask")
    sim.until_phase("buzzer.answering")
    assert sim.eng.round.holder == 2 and sim.eng.round.attempts == []
    say(sim, 2, "give me a hint")  # said again: no loop, it is simply a (wrong) answer
    assert sim.of("buzzer.judged")[-1]["data"] == {"seat": 2, "correct": False, "lockedOut": [2]}


def test_each_player_may_ask_once_a_second_ask_gets_the_no_hints_line_then_an_answer():
    sim = music_sim()
    ask(sim, 0)
    vote(sim, 1, False)  # refused, which still uses Mina's one ask
    sim.until_phase("buzzer.answering")
    say(sim, 0, "hint")
    assert cues(sim, "hint_none") == [("hint_none", {"name": "Mina", "why": "used"})]
    assert [c for c, _ in cues(sim, "hint_ask")] == ["hint_ask"]  # no second consent window
    sim.until_phase("buzzer.answering")
    assert sim.eng.phone_view(0)["own"]["canHint"] is False
    say(sim, 0, "hint")
    assert sim.of("buzzer.judged")[-1]["data"]["correct"] is False


def test_asking_again_at_a_later_level_is_still_once_per_question():
    sim = music_sim()
    ask(sim, 0)
    vote(sim, 1, False)
    sim.until_phase("buzzer.answering")
    say(sim, 0, "nope")
    for seat in (1, 2):
        sim.run_until(lambda: sim.eng.round.armed and sim.eng.round.holder is None, what="buzzers open")
        hold(sim, seat)
        say(sim, seat, "nope")
    at_level(sim, 1)
    hold(sim, 0)  # eligibility was reset for the new level
    assert sim.eng.phone_view(0)["screen"] == "answer_voice" and sim.eng.phone_view(0)["own"]["canHint"] is False
    say(sim, 0, "hint")
    assert cues(sim, "hint_none")[-1][1]["why"] == "used"


def test_an_answer_that_also_says_hint_is_judged_as_an_answer():
    sim = music_sim()
    hold(sim, 0)
    say(sim, 0, "no hint needed, it's Danse Macabre")
    assert sim.of("buzzer.judged")[-1]["data"] == {"seat": 0, "correct": True, "lockedOut": []}
    assert cues(sim, "hint_ask", "hint_grant", "hint_none") == [] and sim.eng.round.hint_asked == set()


def test_an_unclear_or_unvoiced_hint_phrase_is_a_recognition_failure_not_a_request():
    sim = music_sim()
    hold(sim, 0)
    say(sim, 0, "hint", rec="unclear")
    assert not sim.eng.round.hint_request and sim.eng.round.failures == 1
    say(sim, 0, "hint", voiced=False)
    assert not sim.eng.round.hint_request and sim.eng.round.hint_asked == set()


# ---------------------------------------------------------------- the phone path (button and AGREE / NO)
def test_the_hint_button_is_offered_only_to_the_holder_of_a_music_question_who_may_still_ask():
    sim = music_sim()
    assert all("canHint" not in sim.eng.phone_view(s)["own"] for s in (0, 1, 2))
    hold(sim, 0)
    assert sim.eng.phone_view(0)["own"]["canHint"] is True
    assert "canHint" not in sim.eng.phone_view(1)["own"]
    assert sim.act(1, {"type": "hint"}).error == "not_now"  # not the holder
    assert sim.act(0, {"type": "choose_typing"}).ok
    assert sim.eng.phone_view(0)["screen"] == "answer_text" and sim.eng.phone_view(0)["own"]["canHint"] is True
    assert sim.act(0, {"type": "hint"}).ok
    assert sim.eng.phone_view(0)["screen"] == "hint_wait"  # the request is on its way; no second button press


def test_the_button_path_uses_the_same_engine_flow_as_voice_with_a_mock_mc_that_cannot_hear():
    sim = music_sim(voice_input=False)
    hold(sim, 0)
    assert sim.eng.phone_view(0)["screen"] == "answer_text"
    assert sim.act(0, {"type": "hint"}).ok
    sim.run(800)
    assert sim.eng.phase == "buzzer.hint" and sim.last_listen("consent") is None  # nobody to listen to
    assert vote(sim, 1, True).ok and vote(sim, 2, True).ok
    assert grants(sim)[0]["kind"] == "clue"
    sim.until_phase("buzzer.answering")
    assert sim.act(0, {"type": "text_answer", "text": "danse macabre"}).ok
    assert sim.of("buzzer.judged")[-1]["data"]["correct"] is True


def test_a_typed_hint_word_is_an_answer_the_button_is_the_way_to_ask():
    sim = music_sim(voice_input=False)
    hold(sim, 0)
    assert sim.act(0, {"type": "text_answer", "text": "hint"}).ok
    assert sim.of("buzzer.judged")[-1]["data"] == {"seat": 0, "correct": False, "lockedOut": [0]}


def test_the_button_is_refused_outside_the_music_question_and_after_the_limits():
    sim = new_sim(BANK, names=NAMES3, seed=seed_for_track("dm"))
    Bots(sim, ox=lambda s, n: "O", buzz=lambda q, level: 0 if q == 4 and sim.eng.phase == "buzzer.reading" else None)
    sim.until_phase("buzzer.answering")
    assert sim.eng.q.kind == "buzzer" and sim.act(0, {"type": "hint"}).error == "not_now"
    assert "canHint" not in sim.eng.phone_view(0)["own"]  # the button exists only in the music question
    sim2 = music_sim()
    hold(sim2, 0)
    sim2.eng.round.hint_asked.add(0)
    assert sim2.act(0, {"type": "hint"}).error == "no_hints"


# ---------------------------------------------------------------- the automatic ladder is only a longer listen
def test_the_ladder_still_lengthens_the_clip_with_one_short_line_and_no_clue():
    sim = music_sim()
    sim.until_type("score.settled", 5)
    plays = [(m["data"]["level"], m["data"]["startSec"], m["data"]["endSec"]) for m in sim.of("av.play")]
    assert plays == [(0, 12.0, 20.0), (1, 0.0, 16.0), (2, 0.0, 30.0)]
    assert cues(sim, "longer_listen") == [("longer_listen", {"level": 1, "max_level": 2}), ("longer_listen", {"level": 2, "max_level": 2})]
    assert cues(sim, "hint_ask", "hint_grant", "hint_refused", "hint_none") == []


# ---------------------------------------------------------------- privacy
def test_the_clues_and_the_composer_are_not_in_any_cue_facts_until_granted():
    sim = music_sim()
    ask(sim, 0)
    seen = repr([f for c, f in cues(sim)])
    assert CLUE1 not in seen and CLUE2 not in seen and COMPOSER not in seen
    for v in (1, 2):
        vote(sim, v, True)
    assert CLUE1 in repr(grants(sim)) and CLUE2 not in repr(grants(sim)) and COMPOSER not in repr(grants(sim))


def test_captions_of_a_granted_composer_pass_the_filter_only_after_the_grant_and_other_secrets_still_block():
    sim = music_sim()
    eng = sim.eng
    assert not eng.mc_caption(1, f"It's by {COMPOSER}!", True)  # not granted yet: blocked
    assert not eng.mc_caption(2, "It is Danse Macabre!", True)
    for n, seat in enumerate((0, 1, 2)):
        sim.run_until(lambda: sim.eng.round.armed and sim.eng.round.holder is None, what="buzzers open")
        hold(sim, seat)
        say(sim, seat, "hint")
        sim.run(800)
        for v in {0, 1, 2} - {seat}:
            vote(sim, v, True)
        sim.until_phase("buzzer.answering")
        if n < 2:
            assert not eng.mc_caption(10 + n, f"It's by {COMPOSER}!", True)  # the composer is still private after clue 1 and 2
        say(sim, seat, "nope")
    assert eng.round.composer_out
    # (the round object is replaced at the next question; the caption is checked while this one is live)
    assert eng.mc_caption(20, f"It's by {COMPOSER}!", True)
    assert eng.mc_caption(21, CLUE1, True)
    assert not eng.mc_caption(22, "It is Danse Macabre by the composer!", True)  # the title is still secret
    assert not eng.mc_caption(23, "The credit: Danse macabre", True)  # and so is the credit title


def _hint_hook(sim, seed):
    """Players who ask for hints in the music question, by button or by voice, and vote at random."""
    rng = random.Random(seed)
    done = set()

    def hook(s):
        e, r = s.eng, s.eng.round
        if not isinstance(r, BuzzRound) or e.q is None or e.q.kind != "av":
            return
        if e.phase == "buzzer.answering" and r.holder is not None and r.answer is None and not r.hint_request:
            key = ("ask", r.holder, len(r.attempts), e.hint_level)
            if key not in done and e.can_ask_hint(r.holder):
                done.add(key)
                if rng.random() < 0.8:
                    seat = r.holder
                    if rng.random() < 0.5:
                        s.after(300, lambda: s.act(seat, {"type": "hint"}))
                    else:
                        l = s.last_listen("answer")
                        if l is not None and l.seat == seat and r.listen_id == l.listen_id:
                            s.after(300, lambda: e.mc_voice_answer(l.listen_id, "give me a hint", "clear", True) and s.pump())
        if e.phase == "buzzer.hint" and r.consent is not None:
            for v in r.consent.voters:
                key = ("vote", v, r.hints_given, len(r.attempts), e.hint_level)
                if key not in done and v not in r.consent.votes and rng.random() < 0.9:
                    done.add(key)
                    agree = rng.random() < 0.6
                    s.after(rng.choice([200, 500, 900]), lambda v=v, agree=agree: s.act(v, {"type": "hint_vote", "agree": agree}))
    sim.hooks.append(hook)


@pytest.mark.parametrize("players,seed,game_index", [(1, 101, 0), (2, 102, 1), (3, 103, 0), (3, 104, 1), (2, 105, 0), (3, 106, 0), (3, 107, 1), (1, 108, 1)])
def test_full_games_that_use_hints_leak_nothing(players, seed, game_index):
    names = {1: ("Mina",), 2: ("Mina", "Junho"), 3: NAMES3}[players]
    sim = new_sim(BANK, names=names, seed=seed, game_index=game_index)
    random_bots(sim, seed, p_buzz=0.9)
    _hint_hook(sim, seed)
    sim.until_ended()
    assert sim.stream[-1]["type"] == "game.ended" and len(sim.of("answer.revealed")) == 8
    assert_no_leaks(sim)
    assert not any(m["type"] in ("buzzer.hint_request", "hint.consent") for m in sim.stream)
    assert {m["type"] for m in sim.stream if m["type"].startswith("buzzer.")} <= {
        "buzzer.armed", "buzzer.pressed", "buzzer.judged"}  # no hint-specific stream messages


def test_hint_games_across_seeds_do_use_hints_so_the_scan_above_is_not_vacuous():
    total = {"asked": 0, "granted": 0, "refused": 0, "composer": 0}
    for seed in range(200, 208):
        sim = new_sim(BANK, names=NAMES3, seed=seed, game_index=seed % 2)
        random_bots(sim, seed, p_buzz=0.95)
        _hint_hook(sim, seed)
        sim.until_ended()
        assert_no_leaks(sim)
        total["asked"] += len(cues(sim, "hint_ask"))
        total["granted"] += len(grants(sim))
        total["refused"] += len(cues(sim, "hint_refused"))
        total["composer"] += sum(g["kind"] == "composer" for g in grants(sim))
    assert total["granted"] > 2 and total["refused"] > 0 and total["asked"] > 4, total


def test_the_scan_catches_a_clue_handed_out_before_the_grant():
    sim = music_sim()
    sim.until_ended()
    assert_no_leaks(sim)
    from khqs.engine.effects import McSay as S
    sim.mc_fx.append((1, S("t-x", "hint_grant", {"name": "Mina", "how": "solo", "kind": "clue", "text": CLUE1, "number": 1}), 0))
    sim.mc_fx.append((2, S("t-y", "read_ox", {"text": f"{COMPOSER}"}), 0))
    with pytest.raises(AssertionError, match="leaks the hint"):
        assert_no_leaks(sim)
