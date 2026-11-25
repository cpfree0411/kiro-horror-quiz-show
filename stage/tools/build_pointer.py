r"""Pointer beside the lobby start sign (KHQS_v18\pointer_off.png) → pointer_hand, pointer_word + manifest.js entries

The GPT delivery was a plywood picket (board + stick), but the user found the picket crude and asked to use only the hand and the word CLICK! like game UI elements (2026-11-15).
So only two pieces are cut out of the board.
- Hand: close the thick ink outline, flood-fill the outside (board + blue background) from the box edges; what remains inside is the hand.
  The strip of the board's right edge (with the screw) that comes out attached to the finger is removed with a large opening.
- Word: keep the red and the ink around it; drop small specks.
The lit look is done in code (brightness + orange glow), not art. pointer_on.png is not used.

Run: python stage-v3/tools/build_pointer.py   (needs Pillow, numpy, opencv)
Rerunning build_assets_v3.py rewrites manifest.js, so rerun this file after it.
"""
import json
import pathlib
import re

import cv2
import numpy as np
from PIL import Image

SRC = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets" / "KHQS_v18" / "pointer_off.png"
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"

a = np.asarray(Image.open(SRC).convert("RGB")).astype(int)
r, g, b = a[..., 0], a[..., 1], a[..., 2]
lum = (r * 3 + g * 6 + b) / 10
blue = (b > r + 40) & (b > g + 15)


def outside_fill(wall):
    """Flood-fill outside the wall from every point on the box edge. Only the inside enclosed by the wall stays False."""
    ff = (wall * 255).astype(np.uint8)
    h, w = ff.shape
    for x, y in [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]:
        if ff[y, x] == 0:
            cv2.floodFill(ff, np.zeros((h + 2, w + 2), np.uint8), (x, y), 128)
    return ff == 128


def biggest(m):
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    return lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])


def cut(m, box, name, width):
    y0, x0 = box
    al = cv2.GaussianBlur(m.astype(np.float32), (3, 3), 0)
    ys, xs = np.where(al > .02)
    sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
    rgb = a[y0:y0 + m.shape[0], x0:x0 + m.shape[1]][sl]
    im = Image.fromarray(np.dstack([rgb, al[sl] * 255]).astype(np.uint8), "RGBA")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(OUT / f"{name}.webp", "WEBP", quality=90, method=6)
    return {"src": f"assets/{name}.webp", "w": im.width, "h": im.height}


# hand (source box y 250–600, x 230–1100: leave a margin around the hand)
y0, y1, x0, x1 = 250, 600, 230, 1100
dark = ((lum < 95) & ~blue)[y0:y1, x0:x1].astype(np.uint8)
wall = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
hand = biggest(~outside_fill(wall))
core = cv2.morphologyEx(hand.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
hand = biggest(hand & (cv2.dilate(core, np.ones((9, 9), np.uint8)) > 0))
added = {"pointer_hand": cut(hand, (y0, x0), "pointer_hand", 380)}

# word (source box y 570–780, x 130–860)
y0, y1, x0, x1 = 570, 780, 130, 860
red = ((r > 130) & (r - g > 55) & (r - b > 55))[y0:y1, x0:x1]
near = cv2.dilate(red.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
word = ~outside_fill(red | ((lum[y0:y1, x0:x1] < 120) & near))
n, lab, st, _ = cv2.connectedComponentsWithStats(word.astype(np.uint8), 8)
word = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 1500])   # only the six letters; drop the specks
added["pointer_word"] = cut(word, (y0, x0), "pointer_word", 300)

mf = OUT / "manifest.js"
manifest = json.loads(re.search(r"=\s*(\{.*\})\s*;", mf.read_text(encoding="utf-8"), re.S).group(1))
for k in ("pointer_off", "pointer_on"):
    manifest.pop(k, None)
    (OUT / f"{k}.webp").unlink(missing_ok=True)
manifest.update(added)
mf.write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
for k, v in added.items():
    print(k, v["w"], "x", v["h"], (OUT / f"{k}.webp").stat().st_size // 1024, "KB")
