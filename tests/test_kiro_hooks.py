"""The Kiro hooks in .kiro/hooks and the scripts they run (docs/KIRO_USAGE.md)."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS = sorted((REPO / ".kiro" / "hooks").glob("*.json"))
TRIGGERS = {"PreToolUse", "PermissionRequest", "PostToolUse", "SessionStart", "Stop", "SubagentStop", "UserPromptSubmit", "PreTaskExec",
            "PostTaskExec", "PreCompact", "PostCompact", "PostFileCreate", "PostFileSave", "PostFileDelete"}
FILE_TRIGGERS = {"PostFileCreate", "PostFileSave", "PostFileDelete"}


def all_hooks():
    for f in HOOKS:
        for h in json.loads(f.read_text())["hooks"]:
            yield f, h


def test_the_expected_hooks_exist_and_are_well_formed():
    assert {f.stem for f in HOOKS} == {"frozen-boundary", "bank-check", "quick-tests", "stop-gate"}
    for f in HOOKS:
        j = json.loads(f.read_text())
        assert j["version"] == "v1" and j["hooks"], f
    for f, h in all_hooks():
        assert h["name"] and h["trigger"] in TRIGGERS, (f, h)
        assert h["action"]["type"] == "command" and h["action"]["command"].startswith("scripts/"), (f, h)
        if h["trigger"] in FILE_TRIGGERS:
            re.compile(h["matcher"])


def test_every_command_is_an_executable_repo_script():
    for f, h in all_hooks():
        script = REPO / h["action"]["command"].split()[0]
        assert script.is_file() and os.access(script, os.X_OK), script


def matches(hook_name, path):
    for f, h in all_hooks():
        if f.stem == hook_name and h["trigger"] in FILE_TRIGGERS and re.search(h["matcher"], path):
            return True
    return False


@pytest.mark.parametrize("path", ["stage/stage.js", "/srv/x/kiro-horror-quiz-show/stage/assets/lobby.webp", "interface/stage-protocol.schema.json",
                                  "MANIFEST.sha256", "/abs/path/MANIFEST.sha256", "interface/tools/validate.py"])
def test_frozen_boundary_hook_fires_for_frozen_paths(path):
    assert matches("frozen-boundary", path)


@pytest.mark.parametrize("path", ["server/khqs/engine/core.py", "tests/test_guards.py", "README.md", "docs/HANDOFF.md", "banks/en-bank.json", "mystage/x.js"])
def test_frozen_boundary_hook_ignores_other_paths(path):
    assert not matches("frozen-boundary", path)


def test_bank_and_quick_test_hooks_fire_where_they_should():
    for p in ("banks/en-bank.json", "banks/new.json", "media/bwv565.mp3", "server/khqs/content/model.py", "/abs/banks/dev-bank.json"):
        assert matches("bank-check", p), p
    for p in ("README.md", "banks/notes.txt", "server/khqs/engine/core.py"):
        assert not matches("bank-check", p), p
    for p in ("server/khqs/rules/judge.py", "server/khqs/content/bank_io.py", "server/khqs/mc/prompts.py", "server/khqs/mc/voice.py",
              "server/khqs/server/guards.py", "tests/test_rules_judge.py", "tests/test_guards.py", "tests/test_bank_io.py", "tests/test_mc_prompts_voice.py"):
        assert matches("quick-tests", p), p
    for p in ("server/khqs/engine/core.py", "server/khqs/server/app.py", "tests/server/test_live_mc.py"):
        assert not matches("quick-tests", p), p  # the slow parts are not hooked
    stop = [h for f, h in all_hooks() if f.stem == "stop-gate"]
    assert len(stop) == 1 and stop[0]["trigger"] == "Stop"


def run(script, cwd=REPO):
    return subprocess.run([str(cwd / "scripts" / script)], cwd=cwd, capture_output=True, text=True, timeout=120,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def test_check_manifest_passes_on_the_repo_and_detects_changes_and_extras_in_a_copy(tmp_path):
    ok = run("check_manifest.sh")
    assert ok.returncode == 0 and "manifest OK (171 files)" in ok.stdout
    # a tiny copy of the layout: the real stage/ is never touched
    root = tmp_path / "r"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "check_manifest.sh", root / "scripts")
    (root / "stage").mkdir(); (root / "interface").mkdir()
    (root / "stage" / "a.js").write_bytes(b"one")
    (root / "interface" / "b.json").write_bytes(b"two")
    subprocess.run("sha256sum stage/a.js interface/b.json > MANIFEST.sha256", shell=True, cwd=root, check=True)
    assert run("check_manifest.sh", root).returncode == 0
    (root / "stage" / "a.js").write_bytes(b"one!")
    bad = run("check_manifest.sh", root)
    assert bad.returncode == 1 and "FROZEN BOUNDARY BROKEN" in bad.stderr and "a.js" in bad.stderr
    (root / "stage" / "a.js").write_bytes(b"one")
    (root / "stage" / "extra.js").write_bytes(b"x")
    extra = run("check_manifest.sh", root)
    assert extra.returncode == 1 and "not in MANIFEST.sha256" in extra.stderr and "extra.js" in extra.stderr
    (root / "stage" / "extra.js").unlink()
    (root / "interface" / "b.json").unlink()
    gone = run("check_manifest.sh", root)
    assert gone.returncode == 1  # a deleted frozen file


def test_check_banks_passes_and_reports_a_broken_bank_in_a_copy(tmp_path):
    ok = run("check_banks.sh")
    assert ok.returncode == 0 and ok.stdout.count("OK: banks/") == 2
    root = tmp_path / "r"
    shutil.copytree(REPO / "scripts", root / "scripts")
    shutil.copytree(REPO / "server", root / "server", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "media", root / "media")
    (root / "banks").mkdir()
    data = json.loads((REPO / "banks" / "dev-bank.json").read_text())
    data["sets"][0]["buzzers"][0]["category"] = "Mirror Room"
    (root / "banks" / "broken.json").write_text(json.dumps(data))
    bad = run("check_banks.sh", root)
    assert bad.returncode == 1 and "BANK INVALID: banks/broken.json" in bad.stderr and "appears in the category or text" in bad.stderr


def test_the_stop_gate_runs_all_three_checks_quickly():
    import time
    t = time.monotonic()
    r = subprocess.run(["scripts/check_all_quick.sh"], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert time.monotonic() - t < 60
