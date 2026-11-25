"""Compare an engine stream with a scenario file from interface/scenarios (type order and key data)."""
from __future__ import annotations

import json
from pathlib import Path

SCENARIOS = Path(__file__).resolve().parents[2] / "interface" / "scenarios"


def load(name: str, replace: dict | None = None) -> list[dict]:
    text = (SCENARIOS / f"{name}.json").read_text(encoding="utf-8")
    for a, b in (replace or {}).items():
        text = text.replace(a, b)
    return [s["send"] for s in json.loads(text)["steps"] if "send" in s]


def _norm(x):
    """12.0 and 12 are the same JSON number for the stage."""
    if isinstance(x, float) and x == int(x):
        return int(x)
    if isinstance(x, list):
        return [_norm(v) for v in x]
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    return x


def _shape(m: dict, keys: dict) -> tuple:
    t, d = m["type"], m["data"]
    if t == "phase.changed":
        return (t, d["phase"], d["deadline"] is None)
    sel = keys.get(t)
    return (t, json.dumps(_norm({k: d[k] for k in sel}), sort_keys=True, ensure_ascii=False)) if sel else (t,)


def compare(stream, scenario_msgs, *, ignore=(), keys=None, skip_scenario=None, skip_engine=None):
    """Return a list of differences (empty = same flow).

    `ignore`: types dropped on both sides. `skip_scenario` / `skip_engine`: predicates dropping individual
    messages that are an intended divergence (documented in design.md section 9).
    """
    keys = keys or {}
    eng = [m for m in stream if m["type"] not in ignore and m["type"] != "snapshot" and not (skip_engine and skip_engine(m))]
    scn = [m for m in scenario_msgs if m["type"] not in ignore and m["type"] != "snapshot" and not (skip_scenario and skip_scenario(m))]
    a, b = [_shape(m, keys) for m in eng], [_shape(m, keys) for m in scn]
    diffs = []
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        if x != y:
            diffs.append(f"#{i}: engine={x} scenario={y}")
            if len(diffs) >= 6:
                break
    return diffs
