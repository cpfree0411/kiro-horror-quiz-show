"""Validate khqs.stage/1 scenarios and wire examples against the schema.

Usage:  python interface/tools/validate.py            (needs: pip install jsonschema)
Engine side can reuse `check_engine_message()` in its tests.
"""
import json
import pathlib
import sys

from jsonschema import Draft202012Validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "stage-protocol.schema.json").read_text(encoding="utf-8"))


def validator_for(defname):
    return Draft202012Validator({**SCHEMA, "oneOf": [{"$ref": f"#/$defs/{defname}"}]})


SCENARIO = validator_for("scenario")
ENGINE_WIRE = validator_for("engineMessageWire")
STAGE = validator_for("stageMessage")


def errors(v, doc):
    out = []
    for e in sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        # For a oneOf failure, show the most plausible sub-error
        best = e
        if e.context:
            best = min(e.context, key=lambda c: len(list(c.relative_path)) * -1)
        out.append(f"  at {'/'.join(map(str, e.absolute_path)) or '<root>'}: {best.message}")
    return out


def check_engine_message(msg):
    """Wire-level check for one engine → stage message. Returns a list of problems."""
    return errors(ENGINE_WIRE, msg)


def main():
    failed = 0
    for path in sorted((ROOT / "scenarios").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        errs = errors(SCENARIO, doc)
        print(("FAIL " if errs else "ok   ") + path.name, f"({len(doc.get('steps', []))} steps)")
        for e in errs[:10]:
            print(e)
        failed += bool(errs)
    wire = json.loads((ROOT / "examples" / "wire-messages.json").read_text(encoding="utf-8"))
    for side, v in (("engine", ENGINE_WIRE), ("stage", STAGE)):
        for i, msg in enumerate(wire[side]):
            errs = errors(v, msg)
            print(("FAIL " if errs else "ok   ") + f"wire {side}[{i}] {msg['type']}")
            for e in errs[:10]:
                print(e)
            failed += bool(errs)
    print("ALL OK" if not failed else f"{failed} file(s)/message(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
