"""The development bank: banks/dev-bank.json (format khqs.bank/1). Used when no bank file is configured.

The real English bank is a separate file chosen with KHQS_BANK; see docs/QUESTION_BANK_FORMAT.md.
"""
from __future__ import annotations

from pathlib import Path

from ..server.settings import REPO
from .bank_io import load_bank
from .model import ContentBank

DEV_BANK_PATH = REPO / "banks" / "dev-bank.json"


def build_dev_bank(media_dir: Path | None = None) -> ContentBank:
    return load_bank(DEV_BANK_PATH, media_dir or REPO / "media")
