r"""Act 1 decoy plywood characters (KHQS_v16\decoys.png) → decoy_sack, decoy_tophat_skull, decoy_vampire, decoy_bolt + manifest.js entries

The sheet is 2×2: top left one-eye (sack), top right top-hat skull bear, bottom left vampire, bottom right Frankenstein (bolt).
The plywood that pops up instead of the character in the scoreboard window after an answer (stage.js makeSign). Saved at width 360, like the stickers (fan_*_idle).

Run: python stage-v3/tools/build_decoys.py   (needs Pillow, numpy, opencv)
Rerunning build_assets_v3.py rewrites manifest.js, so rerun this file after it.
"""
import json
import pathlib
import re

import cv2
import numpy as np
from PIL import Image

SRC = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets" / "KHQS_v16" / "decoys.png"
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"


def key(im):
    """Make the blue background transparent (same as build_bats_pumpkins.py: split by colour ratio)."""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    strict = (b > 130) & (b - r > 70) & (b - g > 35) & (g > r + 15)
    bg = a[strict].mean(0)
    bb = np.maximum(b, 1.0)
    c = np.abs(r / bb - bg[0] / bg[2]) + np.abs(g / bb - bg[1] / bg[2])
    alpha = np.clip((c - 0.10) / 0.30, 0, 1)
    alpha[alpha < 0.04] = 0
    al = np.maximum(alpha, 0.05)[..., None]
    fg = np.clip((a - (1 - alpha[..., None]) * bg) / al, 0, 255)
    fg = np.where(alpha[..., None] >= 0.999, a, fg)
    return np.dstack([fg, alpha * 255]).astype(np.uint8)


rgba = key(Image.open(SRC))
solid = (rgba[..., 3] > 40).astype(np.uint8)
n, lab, stats, _ = cv2.connectedComponentsWithStats(cv2.dilate(solid, np.ones((7, 7), np.uint8)), 8)
parts = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 20000]
assert len(parts) == 4, f"expected four boards, got {len(parts)}"
H = rgba.shape[0]
parts.sort(key=lambda i: (stats[i, 1] + stats[i, 3] / 2 > H / 2, stats[i, 0]))   # top row first, left to right

added = {}
for fan, i in zip(["sack", "tophat_skull", "vampire", "bolt"], parts):
    x, y, w, h = stats[i, :4]
    p = rgba[y:y + h, x:x + w].copy()
    p[..., 3] = np.where(lab[y:y + h, x:x + w] == i, p[..., 3], 0)
    ys, xs = np.where(p[..., 3] > 8)
    p = p[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    im = Image.fromarray(p, "RGBA")
    im = im.resize((360, round(im.height * 360 / im.width)), Image.LANCZOS)
    name = f"decoy_{fan}"
    im.save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)
    added[name] = {"src": f"assets/{name}.webp", "w": im.width, "h": im.height}

mf = OUT / "manifest.js"
manifest = json.loads(re.search(r"=\s*(\{.*\})\s*;", mf.read_text(encoding="utf-8"), re.S).group(1))
manifest.update(added)
mf.write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
for k, v in added.items():
    print(k, v["w"], "x", v["h"], (OUT / f"{k}.webp").stat().st_size // 1024, "KB")
