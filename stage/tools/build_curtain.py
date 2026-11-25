r"""Curtain before the finale (KHQS_v14) → curtain, sign_winner, sign_score + manifest.js entries

curtain     : the left half of the curtain. The right side is the free edge (gold cord), the bottom the fringe. Mirrored for the right side.
              Slightly wider than half the screen (800); width and height scaled separately so the fringe hangs at the bottom edge of the screen.
sign_winner : hanging sign AND THE WINNER IS…   sign_score : YOUR FINAL SCORE… (solo game)
              ropes in the manifest = the horizontal positions of the two ropes (fraction of the art width). The code draws the ropes up from there.

Run: python stage-v3/tools/build_curtain.py   (needs Pillow, numpy, opencv)
Rerunning build_assets_v3.py rewrites manifest.js, so rerun this file after it.
"""
import json
import pathlib
import re

import cv2
import numpy as np
from PIL import Image

SRC = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets" / "KHQS_v14"
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
    fg = np.clip((a - (1 - alpha[..., None]) * bg) / al, 0, 255)
    fg = np.where(alpha[..., None] >= 0.999, a, fg)
    return np.dstack([fg, alpha * 255]).astype(np.uint8)


def bbox(part):
    solid = cv2.morphologyEx((part[..., 3] > 40).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    ys, xs = np.where(solid)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def save(name, im, **extra):
    im.save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)
    added[name] = {"src": f"assets/{name}.webp", "w": im.width, "h": im.height, **extra}


# Curtain: crop to the cloth, width 836 (half 800 + overlap), height 906 (the fringe hangs at the bottom edge)
c = key(Image.open(SRC / "curtain_panel.png"))
x0, y0, x1, y1 = bbox(c)
c = c[0:y1 + 2, 0:x1 + 2]
c[:, :8, 3] = np.maximum(c[:, :8, 3], 255 * (c[:, 8:9, 3] > 128))        # the left end is cloth continuing off screen: no gaps
save("curtain", Image.fromarray(c, "RGBA").resize((836, 906), Image.LANCZOS))

# Signs: top (AND THE WINNER IS…), bottom (YOUR FINAL SCORE…)
s = key(Image.open(SRC / "winner_signs.png"))
rows = np.where((s[..., 3] > 40).sum(1) < 5)[0]
mid = [r for r in rows if s.shape[0] * .35 < r < s.shape[0] * .65]
cut = mid[len(mid) // 2]
for name, part in (("sign_winner", s[:cut]), ("sign_score", s[cut:])):
    x0, y0, x1, y1 = bbox(part)
    p = part[y0:y1, x0:x1]
    top = np.where(p[:6, :, 3].max(0) > 40)[0]                              # what touches the top row is the two ropes
    split = (top.min() + top.max()) / 2
    ropes = [round(float(top[top < split].mean() / p.shape[1]), 4), round(float(top[top > split].mean() / p.shape[1]), 4)]
    im = Image.fromarray(p, "RGBA")
    im = im.resize((760, round(im.height * 760 / im.width)), Image.LANCZOS)
    save(name, im, ropes=ropes)

mf = OUT / "manifest.js"
manifest = json.loads(re.search(r"=\s*(\{.*\})\s*;", mf.read_text(encoding="utf-8"), re.S).group(1))
manifest.update(added)
mf.write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
for k, v in added.items():
    print(k, v["w"], v["h"], (OUT / f"{k}.webp").stat().st_size, v.get("ropes", ""))
