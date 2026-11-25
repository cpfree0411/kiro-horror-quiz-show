"""P0: repository hygiene. No key material in the tree; env files stay ignored."""
import re
import subprocess

KEY_PATTERN = re.compile(rb"AIza[0-9A-Za-z_\-]{35}")
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
BINARY_EXT = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".ogg", ".woff", ".woff2", ".ttf", ".mp4"}


def test_no_google_api_key_shaped_strings(repo):
    hits = []
    for p in repo.rglob("*"):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(repo).parts) or p.suffix.lower() in BINARY_EXT:
            continue
        if KEY_PATTERN.search(p.read_bytes()):
            hits.append(p.relative_to(repo).as_posix())
    assert hits == []


def test_env_files_are_git_ignored(repo):
    for name in (".env", ".env.local", "server/.env", "x.env"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=repo)
        assert r.returncode == 0, f"{name} is not ignored"
