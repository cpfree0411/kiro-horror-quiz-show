"""Verify MANIFEST.sha256 in pure Python (same result as `sha256sum -c`), plus extra-file detection.

`sha256sum -c` cannot see files that were added under stage/ or interface/, so this also
compares the file set against the manifest.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

FROZEN_DIRS = ("stage", "interface")


def read_manifest(manifest: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for n, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if not sep or len(digest) != 64:
            raise ValueError(f"{manifest.name}:{n}: not in sha256sum format")
        if rel in entries:
            raise ValueError(f"{manifest.name}:{n}: duplicate path {rel}")
        entries[rel] = digest
    return entries


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(root: Path, manifest_name: str = "MANIFEST.sha256") -> list[str]:
    """Return a list of problems; empty means the frozen tree matches the manifest exactly."""
    entries = read_manifest(root / manifest_name)
    problems: list[str] = []
    for rel, digest in sorted(entries.items()):
        path = root / rel
        if not path.is_file():
            problems.append(f"missing: {rel}")
        elif sha256_file(path) != digest:
            problems.append(f"modified: {rel}")
    on_disk = {
        p.relative_to(root).as_posix()
        for d in FROZEN_DIRS
        if (root / d).is_dir()
        for p in (root / d).rglob("*")
        if p.is_file() or p.is_symlink()
    }
    for rel in sorted(on_disk - entries.keys()):
        problems.append(f"extra (not in manifest): {rel}")
    return problems
