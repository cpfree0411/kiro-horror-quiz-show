"""Lobby: names, seats, fans, credentials, start."""
import json
import random

import pytest

from support.content_fixture import BANK
from support.harness import Sim, new_sim

FANS = {"vampire", "sack", "bolt", "tophat_skull"}


def lobby(**kw):
    return Sim(BANK, **kw)


@pytest.mark.parametrize("name,err", [
    ("", "TYPE A NAME"), ("   ", "TYPE A NAME"), (None, "TYPE A NAME"), (5, "TYPE A NAME"),
    ("A" * 13, "NAME TOO LONG"), ("bad\nname", "NO NAMES LIKE THAT"), ("a\x00b", "NO NAMES LIKE THAT"),
    ("!!!", "NO NAMES LIKE THAT"),
])
def test_bad_names(name, err):
    r = lobby().join(name)
    assert not r.ok and r.error == err


def test_names_are_trimmed_unique_any_script_and_shown_as_typed():
    sim = lobby()
    assert sim.join("  Mina  ").ok
    assert sim.eng.players[0].name == "Mina"
    assert sim.join("MINA").error == "THAT NAME IS TAKEN"  # case-folded
    assert sim.join("ＭＩＮＡ").error == "THAT NAME IS TAKEN"  # NFKC
    assert sim.join("민아").ok and sim.eng.players[1].name == "민아"
    assert sim.join("A" * 12).ok  # 12 is the limit
    assert sim.join("Zed").error == "HOUSE FULL"


def test_lowest_free_seat_distinct_fans_from_the_four_with_art_and_mode():
    sim = lobby()
    sim.join("A")
    assert sim.eng.mode == "solo"
    sim.join("B")
    sim.join("C")
    assert sorted(sim.eng.players) == [0, 1, 2] and sim.eng.mode == "competitive"
    fans = [p.fan for p in sim.eng.players.values()]
    assert len(set(fans)) == 3 and set(fans) <= FANS
    seats = sim.eng.snapshot()["data"]["seats"]
    assert len(seats) == 3 and [s["seat"] for s in seats] == [0, 1, 2]


def test_fans_are_seeded():
    def fans(seed):
        s = Sim(BANK, seed=seed)
        for n in "ABC":
            s.join(n)
        return [p.fan for p in s.eng.players.values()]
    assert fans(5) == fans(5)
    assert len({tuple(fans(s)) for s in range(20)}) > 1


def test_credentials_are_private_and_unique():
    sim = lobby()
    for n in ("A", "B"):
        sim.join(n)
    creds = [p.credential for p in sim.eng.players.values()]
    assert len(set(creds)) == 2 and all(creds)
    assert sim.eng.seat_for_credential(creds[1]) == 1 and sim.eng.seat_for_credential("nope") is None
    sim.start()
    sim.until_type("act.started")
    everything = json.dumps([sim.stream, sim.snapshots, [v for _, v in sim.views], [m for _, m in sim.directs]], ensure_ascii=False)
    assert not any(c in everything for c in creds)
    assert "credential" not in everything


def test_start_rules_and_join_after_start():
    sim = lobby()
    assert sim.eng.start().error == "NEED A PLAYER"
    sim.join("A")
    assert sim.start().ok
    assert sim.eng.start().error == "SHOW ALREADY STARTED"
    assert sim.join("B").error == "SHOW IN PROGRESS"
    assert [m["data"]["phase"] for m in sim.of("phase.changed")][:2] == ["lobby", "opening"]


def test_credential_tokens_do_not_come_from_the_seeded_rng():
    # the default factory must be unguessable: two engines with the same seed get different credentials
    import secrets as _s  # noqa: F401
    from khqs.clock import FakeClock
    from khqs.engine.core import Engine
    a = Engine(BANK, FakeClock(), random.Random(1))
    b = Engine(BANK, FakeClock(), random.Random(1))
    a.join("A"); b.join("A")
    assert a.players[0].credential != b.players[0].credential and len(a.players[0].credential) >= 20


def test_seat_joined_message_is_public_and_complete():
    sim = lobby()
    sim.join("Mina")
    m = sim.of("seat.joined")[0]
    p = m["data"]["player"]
    assert m["data"]["seat"] == 0 and set(p) == {"id", "name", "fanType", "score", "rank", "connected"}
    assert p["score"] == 0 and p["rank"] == 1 and p["connected"] is True


def test_different_games_alternate_sets_and_have_their_own_ids():
    a = new_sim(BANK, names=("A",), game_index=0)
    b = new_sim(BANK, names=("A",), game_index=1)
    assert a.eng.content.set_id == "set-a" and b.eng.content.set_id == "set-b"
    assert a.eng.game_id != b.eng.game_id
