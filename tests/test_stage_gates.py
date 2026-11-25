"""Gate rules (interface section 4, rules section 4) and stage intake (section 2, 3.3)."""
from khqs.engine.effects import McSay
from support.content_fixture import BANK
from support.harness import Sim, new_sim


def manual(names=("Mina",), **kw):
    sim = Sim(BANK, **kw)
    for n in names:
        sim.join(n)
    sim.auto_ack = False
    sim.start()
    return sim


def open_gate(sim):
    return sim.eng.gate


def ack(sim, g, **over):
    data = {"gate": g.id, "sseq": g.sseq}
    data.update(over)
    sim.stage_send("stage.beat_done", data)


def last_direct(sim):
    return sim.directs[-1][1]


def test_gate_ids_follow_sseq_and_one_gate_at_a_time():
    sim = new_sim(BANK, names=("Mina", "Junho"))
    sim.until_ended()
    gates = [m for m in sim.stream if "gate" in m]
    assert gates and all(m["gate"]["id"] == f"g-{m['sseq']}" for m in gates)
    assert all(500 <= m["gate"]["timeoutMs"] <= 90000 for m in gates)
    # a gate message is never sent while another is open: every earlier gate was closed first
    assert [m["sseq"] for m in sim.stream] == list(range(1, len(sim.stream) + 1))


def test_wrong_id_wrong_sseq_and_viewer_acks_change_nothing():
    sim = manual()
    g = open_gate(sim)
    assert g.type == "show.opening"
    n = len(sim.stream)
    sim.stage_send("stage.beat_done", {"gate": "g-999", "sseq": g.sseq})
    assert last_direct(sim)["type"] == "error" and last_direct(sim)["data"]["code"] == "unknown_gate"
    ack(sim, g, sseq=g.sseq + 1)
    assert last_direct(sim)["data"]["code"] == "gate_mismatch"
    sim.hello(conn="viewer-1", role="viewer")
    before = len(sim.directs)
    sim.stage_send("stage.beat_done", {"gate": g.id, "sseq": g.sseq}, conn="viewer-1")
    assert len(sim.directs) == before  # ignored silently
    sim.run(5_000)
    assert open_gate(sim) is g and not g.acked and len(sim.stream) == n


def test_matching_ack_closes_and_duplicates_and_stale_acks_are_harmless():
    sim = manual()
    g = open_gate(sim)
    ack(sim, g)
    sim.run(100)
    assert sim.eng.gate is not g  # closed; the next gate (act.started) is open now
    g2 = sim.eng.gate
    assert g2 is None and sim.eng.phase == "opening"  # the greeting is playing; no gate is open
    n = len(sim.stream)
    ack(sim, g)  # duplicate / stale ack of the closed gate
    assert last_direct(sim)["data"]["code"] == "unknown_gate"
    assert len(sim.stream) == n and (g2 is None or not g2.acked)


def test_safety_timeout_is_timeout_ms_plus_25s_and_game_never_stops():
    sim = manual()
    g = open_gate(sim)
    opened = sim.clock.now_ms()
    sim.run(g.timeout_ms + 24_900)
    assert sim.eng.gate is g
    sim.run(200)
    assert sim.eng.gate is not g
    assert g.safety_at - opened == 60_000 + 25_000


def test_reaction_starts_only_after_ack_and_gate_waits_for_playback():
    sim = manual(say_ms=3000)
    ack(sim, open_gate(sim))
    sim.run(100)
    sim.run_until(lambda: sim.eng.gate and sim.eng.gate.type == "act.started", what="act gate")
    g = sim.eng.gate
    sim.run(2_000)
    assert not [1 for _, e, _t in sim.mc_fx if isinstance(e, McSay) and e.cue == "act_intro"]  # no ack yet
    t_ack = sim.clock.now_ms()
    ack(sim, g)
    said = [(t, e) for _, e, t in sim.mc_fx if isinstance(e, McSay) and e.cue == "act_intro"]
    assert len(said) == 1 and said[0][0] == t_ack
    sim.run(2_900)
    assert sim.eng.gate is g  # acked but the MC is still talking
    sim.run(200)
    assert sim.eng.gate is not g


def test_game_continues_with_no_stage_connected_at_all():
    sim = Sim(BANK, stage=False)
    sim.join("Mina")
    sim.start()
    assert not sim.eng.has_primary()
    t0 = sim.clock.now_ms()
    sim.until_type("act.started")
    assert sim.clock.now_ms() - t0 >= 85_000  # opening gate waited out its safety timeout (60 s + 25 s)


def test_hello_always_gets_a_snapshot_and_second_primary_becomes_viewer():
    sim = new_sim(BANK, names=("Mina",), start=False)
    assert sim.directs[0][1]["type"] == "snapshot"
    assert sim.hello(conn="tab-2", role="primary") == "viewer"
    kinds = [m["type"] for c, m in sim.directs if c == "tab-2"]
    assert kinds == ["snapshot", "error"]
    assert sim.directs[-1][1]["data"]["code"] == "primary_taken"
    sim.eng.stage_disconnect("stage-1")  # the primary leaves: the slot frees
    assert sim.hello(conn="tab-3", role="primary") == "primary"
    assert sim.hello(conn="tab-2", role="primary") == "viewer"  # a viewer is not promoted automatically
    assert sim.hello(conn="tab-3", role="primary") == "primary"  # the same socket may hello again


def test_ping_pong_need_snapshot_media_ready_and_unknown_socket():
    sim = new_sim(BANK, names=("Mina",), start=False)
    sim.stage_send("stage.ping", {"clientTime": 51234.5})
    pong = last_direct(sim)
    assert pong == {"proto": "khqs.stage/1", "type": "pong", "data": {"clientTime": 51234.5, "serverTime": sim.clock.now_ms()}}
    sim.stage_send("stage.need_snapshot", {"lastSseq": 1, "receivedSseq": 5})
    assert last_direct(sim)["type"] == "snapshot"
    sim.stage_send("stage.media_ready", {"assetIds": ["a-3f9c1d2e7b40"]})
    assert "a-3f9c1d2e7b40" in sim.eng.media_ready
    sim.eng.stage_message("ghost", {"proto": "khqs.stage/1", "type": "stage.ping", "data": {"clientTime": 1}})
    sim.pump()
    assert last_direct(sim)["data"]["code"] == "hello_required"
    sim.eng.stage_message("stage-1", "not a dict")
    sim.pump()
    assert last_direct(sim)["data"]["code"] == "bad_message"
    sim.hello(conn="v", role="viewer")
    sim.stage_send("stage.need_snapshot", {"lastSseq": 0, "receivedSseq": 2}, conn="v")
    assert last_direct(sim)["type"] == "snapshot"  # viewers may ask for snapshots


def test_pump_keeps_running_when_every_stage_is_gone():
    sim = Sim(BANK, stage=True)
    sim.join("Mina")
    sim.start()
    sim.eng.stage_disconnect("stage-1")
    assert sim.eng.next_due() is not None  # the engine still has a deadline for the outer loop to sleep on
