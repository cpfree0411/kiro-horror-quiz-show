"""Serving the frozen stage: injection of one script tag, an allowlist, and the opaque media route."""
from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path

from ..content.dev_bank import MEDIA_FILES

WEB = Path(__file__).resolve().parent / "web"
INDEX_ANCHOR = '<script src="mock-engine.js"></script>'
INDEX_TAG = '<script src="/play/link.js"></script>'
TICKET_ANCHOR = "</head>"
TICKET_TAG = '<script src="/play/ticket-hook.js"></script>\n'
ASSET_ID = re.compile(r"^a-[0-9a-f]{8,32}$")
STATIC_TOP = {"stage.js", "stage.css", "sound.js", "sound-files.js", "scenarios.js", "mock-engine.js", "qr.js"}
STATIC_EXT = {".js", ".css", ".webp", ".png", ".ogg", ".mp3", ".json", ".woff2"}


class InjectionError(RuntimeError):
    pass


def inject_once(html: str, anchor: str, tag: str, after: bool) -> str:
    if html.count(anchor) != 1:
        raise InjectionError(f"expected exactly one {anchor!r} in the stage page, found {html.count(anchor)}")
    return html.replace(anchor, anchor + tag if after else tag + anchor)


def index_html(stage_dir: Path) -> bytes:
    text = (stage_dir / "index.html").read_text(encoding="utf-8")
    return inject_once(text, INDEX_ANCHOR, "\n" + INDEX_TAG, after=True).encode("utf-8")


def ticket_html(stage_dir: Path) -> bytes:
    text = (stage_dir / "ticket.html").read_text(encoding="utf-8")
    return inject_once(text, TICKET_ANCHOR, TICKET_TAG, after=False).encode("utf-8")


def static_path(stage_dir: Path, rel: str) -> Path | None:
    """A frozen stage file that may be served, or None. Allowlist: top-level scripts/styles and assets/**."""
    parts = [p for p in rel.split("/") if p]
    if not parts or any(p in (".", "..") or p.startswith(".") or "\\" in p for p in parts):
        return None
    if len(parts) == 1:
        if parts[0] not in STATIC_TOP:
            return None
    elif parts[0] != "assets":
        return None
    p = stage_dir.joinpath(*parts)
    try:
        p.resolve().relative_to(stage_dir.resolve())
    except ValueError:
        return None
    if p.suffix.lower() not in STATIC_EXT or not p.is_file():
        return None
    return p


def media_type(p: Path) -> str:
    if p.suffix == ".js":
        return "text/javascript"
    return mimetypes.guess_type(str(p))[0] or "application/octet-stream"


def link_js(joinUrl: str, mc: str) -> bytes:
    cfg = {"joinUrl": joinUrl, "mc": mc, "liveVoice": mc == "live"}
    src = (WEB / "link.js").read_text(encoding="utf-8")
    if "__KHQS_CONFIG__" not in src:
        raise InjectionError("link.js lost its config placeholder")
    return src.replace("__KHQS_CONFIG__", json.dumps(cfg)).encode("utf-8")


class MediaStore:
    """Music files by opaque id. No title, file name or tag leaves the server."""

    def __init__(self, media_dir: Path, mapping: dict[str, str] | None = None) -> None:
        self.dir, self.mapping = media_dir, mapping or dict(MEDIA_FILES)

    def path_for(self, asset_id: str) -> Path | None:
        name = self.mapping.get(asset_id) if ASSET_ID.match(asset_id) else None
        p = self.dir / name if name else None
        return p if p and p.is_file() else None
