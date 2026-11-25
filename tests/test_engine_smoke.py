from support.content_fixture import BANK
from support.harness import new_sim


def test_lobby_snapshot_and_join():
    sim = new_sim(BANK, names=("Mina",), start=False)
    assert sim.directs[0][1]["type"] == "snapshot" and sim.directs[0][1]["sseq"] == 1
    snap = sim.snapshots[-1]
    assert snap["data"]["game"]["phase"] == "lobby"
    assert [s["status"] for s in snap["data"]["seats"]] == ["vacant", "occupied", "vacant"]
