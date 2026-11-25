"""Validate a question bank file:  python -m khqs.content.check banks/dev-bank.json  (exit 1 on errors)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..server.settings import REPO
from .bank_io import check_bank_file


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate a Kiro Horror Quiz Show question bank (format khqs.bank/1).")
    ap.add_argument("bank", type=Path)
    ap.add_argument("--media-dir", type=Path, default=REPO / "media")
    a = ap.parse_args(argv)
    bank, errors, warnings = check_bank_file(a.bank, a.media_dir)
    for w in warnings:
        print(f"WARNING {w}")
    for e in errors:
        print(f"ERROR   {e}")
    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s): {a.bank} is NOT usable")
        return 1
    print(f"OK: {a.bank}: {len(bank.sets)} sets, {len(bank.tracks)} tracks, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
