"""P0: the frozen boundary. MANIFEST.sha256 must keep passing; the validator must stay green."""
import json
import shutil
import subprocess
import sys

import pytest

from manifest_check import verify_manifest

TARGETS = ("stage", "interface")


def test_manifest_matches_exactly(repo):
    assert verify_manifest(repo) == []


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="sha256sum not installed")
def test_sha256sum_c_passes(repo):
    r = subprocess.run(["sha256sum", "-c", "MANIFEST.sha256"], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


def test_manifest_covers_every_frozen_file(repo):
    # 171 files per handoff PACKAGE.md; guards against a manifest that silently shrank.
    lines = [l for l in (repo / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 171
    assert all(l.split("  ", 1)[1].startswith(("stage/", "interface/")) for l in lines)


def test_checker_detects_modified_missing_and_extra(tmp_path, repo):
    # The checker itself must not be vacuous: tamper with a small copy.
    root = tmp_path / "r"
    (root / "stage").mkdir(parents=True)
    (root / "interface").mkdir()
    (root / "stage" / "a.js").write_bytes(b"one")
    (root / "interface" / "b.json").write_bytes(b"two")
    import hashlib
    (root / "MANIFEST.sha256").write_text(
        f"{hashlib.sha256(b'one').hexdigest()}  stage/a.js\n{hashlib.sha256(b'two').hexdigest()}  interface/b.json\n"
    )
    assert verify_manifest(root) == []
    (root / "stage" / "a.js").write_bytes(b"one\r\n")
    (root / "interface" / "b.json").unlink()
    (root / "stage" / "new.js").write_bytes(b"x")
    assert verify_manifest(root) == [
        "missing: interface/b.json",
        "modified: stage/a.js",
        "extra (not in manifest): stage/new.js",
    ]


def test_validate_py_all_ok(repo):
    r = subprocess.run([sys.executable, "-B", "interface/tools/validate.py"], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert r.stdout.strip().splitlines()[-1] == "ALL OK"


def test_check_engine_message_is_usable_and_not_vacuous(repo):
    sys.path.insert(0, str(repo / "interface" / "tools"))
    try:
        import validate
    finally:
        sys.path.pop(0)
    examples = json.loads((repo / "interface" / "examples" / "wire-messages.json").read_text(encoding="utf-8"))
    for msg in examples["engine"]:
        assert validate.check_engine_message(msg) == [], msg["type"]
    bad = {"proto": "khqs.stage/1", "type": "ox.submitted", "sseq": 1, "at": 1, "data": {"seat": 0, "choice": "O"}}
    assert validate.check_engine_message(bad) != []  # a pick in ox.submitted must fail (interface §5)
