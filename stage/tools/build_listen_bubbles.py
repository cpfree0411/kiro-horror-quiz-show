r"""LISTEN art and speech bubbles (KHQS_v11) → listen, bubble_s, bubble_l + manifest.js entries

listen   : art hung on the paper board in act 2 while the question is hidden (gramophone, notes, LISTEN!, listening ghost).
bubble_s : short speech bubble. bubble_l : long speech bubble. Both have the tail at bottom left.
           The manifest records the text area (inner) and the tail tip (tip) as fractions of the art size.

Run: python stage-v3/tools/build_listen_bubbles.py   (needs Pillow, numpy, opencv)
Rerunning build_assets_v3.py rewrites manifest.js, so rerun this file after it.
"""
import json
import pathlib
import re

import cv2
import numpy as np
from PIL import Image


SRC = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets" / "KHQS_v11" / "listen_bubbles.png"
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"
added = {}


def key(im):
    """Make the blue background transparent. It splits by colour ratio, not brightness, so shadows on the background go too."""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    strict = (b > 130) & (b - r > 70) & (b - g > 35) & (g > r + 15)
    bg = a[strict].mean(0)
    bb = np.maximum(b, 1.0)
    c = np.abs(r / bb - bg[0] / bg[2]) + np.abs(g / bb - bg[1] / bg[2])
    alpha = np.clip((c - 0.10) / 0.30, 0, 1)
    alpha[alpha < 0.04] = 0
    al = np.maximum(alpha, 0.05)[..., None]
    fg = np.clip((a - (1 - alpha[..., None]) * bg) / al, 0, 255)      # remove the blue spill at the edges
    fg = np.where(alpha[..., None] >= 0.999, a, fg)
    return np.dstack([fg, alpha * 255]).astype(np.uint8)


rgba = key(Image.open(SRC))
assert rgba.shape[:2] == (1024, 1536), rgba.shape


def cut(name, box, max_side, bubble=False):
    """Crop one region of the sheet to the art and save it. Separate bits inside the region (notes, emphasis lines) go with it."""
    x0, y0, x1, y1 = box
    part = rgba[y0:y1, x0:x1]
    solid = (part[..., 3] > 40).astype(np.uint8)
    solid = cv2.morphologyEx(solid, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    ys, xs = np.where(solid)
    bx0, by0, bx1, by1 = xs.min() - 3, ys.min() - 3, xs.max() + 4, ys.max() + 4
    im = Image.fromarray(part[by0:by1, bx0:bx1], "RGBA")
    extra = {}
    if bubble:
        n, lab, stats, _ = cv2.connectedComponentsWithStats(solid[by0:by1, bx0:bx1])
        big = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])      # the paper body (the emphasis lines are separate)
        x, y, w, h = stats[big, :4]
        body = lab == big
        ty = np.where(body.any(1))[0].max()                                 # tail tip: the lowest point of the body
        tx = np.where(body[ty])[0].mean()
        W, H = im.size
        extra["inner"] = [round(float(v), 4) for v in ((x + .13 * w) / W, (y + .15 * h) / H, (x + .87 * w) / W, (y + .73 * h) / H)]
        extra["tip"] = [round(float(tx / W), 4), round(float(ty / H), 4)]
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    im.save(OUT / f"{name}.webp", "WEBP", quality=90, method=6)
    added[name] = {"src": f"assets/{name}.webp", "w": im.width, "h": im.height, **extra}


cut("listen", (0, 0, 1536, 500), 1000)
cut("bubble_s", (0, 520, 552, 1024), 420, bubble=True)
cut("bubble_l", (552, 520, 1536, 1024), 720, bubble=True)

mf = OUT / "manifest.js"
manifest = json.loads(re.search(r"=\s*(\{.*\})\s*;", mf.read_text(encoding="utf-8"), re.S).group(1))
manifest.update(added)
mf.write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
for k, v in added.items():
    print(k, v["w"], v["h"], (OUT / f"{k}.webp").stat().st_size, v.get("inner", ""), v.get("tip", ""))
