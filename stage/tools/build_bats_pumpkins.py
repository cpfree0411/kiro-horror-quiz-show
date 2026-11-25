r"""Bat swarm and pumpkin pile transitions (KHQS_v15) → bat_0..2, bat_big, pk_0..5, pk_bit_0..8 + manifest.js entries

bat_0..2 : three wing poses of the small bat (wings up, side, down). Placed on same-size canvases with the body centres aligned,
           so the body does not jump when they alternate. body in the manifest = body centre (fraction of the canvas).
bat_big  : the big bat flying at the screen. body = body centre and radius (fraction of the art width). The code uses it to set the scale that covers the screen.
pk_0..5  : six pumpkins (grin, surprised, sleepy, wink, tongue out, dizzy). r = collision radius (fraction of the art width).
pk_bit_* : debris. 0..3 rind bits, 4..6 seeds, 7..8 dry leaves.

Run: python stage-v3/tools/build_bats_pumpkins.py   (needs Pillow, numpy, opencv)
Rerunning build_assets_v3.py rewrites manifest.js, so rerun this file after it.
"""
import json
import pathlib
import re

import cv2
import numpy as np
from PIL import Image

SRC = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets" / "KHQS_v15"
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


def pieces(rgba, join=9, min_area=600):
    """Separate pieces. Dilate a little so a thin vine cut off from the body still groups as one piece."""
    solid = (rgba[..., 3] > 40).astype(np.uint8)
    grown = cv2.dilate(solid, np.ones((join, join), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(grown, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        m = (lab[y:y + h, x:x + w] == i)
        p = rgba[y:y + h, x:x + w].copy()
        p[..., 3] = np.where(m, p[..., 3], 0)
        out.append(dict(x=x, y=y, w=w, h=h, img=p))
    return out


def trim(p, pad=2):
    ys, xs = np.where(p[..., 3] > 8)
    return p[max(0, ys.min() - pad):ys.max() + 1 + pad, max(0, xs.min() - pad):xs.max() + 1 + pad]


def save(name, arr, width=None, **extra):
    im = Image.fromarray(arr, "RGBA")
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)
    added[name] = {"src": f"assets/{name}.webp", "w": im.width, "h": im.height, **extra}


def body_center(p):
    """Bat body: a round blob darker and less red than the wings. Centre and radius of the largest dark blob."""
    a = p[..., :3].astype(np.float32)
    lum = a @ np.array([.299, .587, .114], np.float32)
    dark = ((lum < 75) & (p[..., 3] > 200)).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lab, stats, cents = cv2.connectedComponentsWithStats(dark, 8)
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    cx, cy = cents[i]
    r = np.sqrt(stats[i, cv2.CC_STAT_AREA] / np.pi)
    return float(cx), float(cy), float(r)


# ---------- Bats ----------
bats = pieces(key(Image.open(SRC / "bats.png")))
bats.sort(key=lambda q: q["w"] * q["h"])
big, small = bats[-1], sorted(bats[:-1], key=lambda q: q["x"])
assert len(small) == 3, f"expected three small bats, got {len(small)}"

frames = [trim(q["img"]) for q in small]
# Align the bodies: use the face and body of the middle frame (wings to the side) as the template and find the same spot in the other two (sizes differ slightly, so match the scale too)
mx, my, _ = body_center(frames[1])
ref = frames[1][int(my) - 70:int(my) + 85, int(mx) - 62:int(mx) + 62]
refc = cv2.cvtColor(ref[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
refm = (ref[..., 3] > 200).astype(np.float32)
cens = []
for n, f in enumerate(frames):
    if n == 1:
        cens.append((mx, my, 1.0)); continue
    best = None
    for s in np.arange(.82, 1.2, .01):
        g = cv2.cvtColor(cv2.resize(f[..., :3], None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY).astype(np.float32)
        res = cv2.matchTemplate(g, refc, cv2.TM_CCORR_NORMED, mask=refm)
        _, v, _, loc = cv2.minMaxLoc(res)
        if best is None or v > best[0]:
            best = (v, s, loc)
    v, s, (lx, ly) = best
    cens.append(((lx + 62) / s, (ly + 70) / s, float(s)))
    print(f"bat frame {n}: match {v:.3f} scale {s:.2f}")
frames = [cv2.resize(f, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s != 1 else f for f, (_, _, s) in zip(frames, cens)]
cens = [(cx * s, cy * s, 0) for cx, cy, s in cens]
# align the body centres on the same canvas
L = max(c[0] for c in cens); R = max(f.shape[1] - c[0] for f, c in zip(frames, cens))
T = max(c[1] for c in cens); B = max(f.shape[0] - c[1] for f, c in zip(frames, cens))
cw, ch = int(np.ceil(L + R)) + 2, int(np.ceil(T + B)) + 2
SW = 300                                                     # saved width: about the largest it ever appears on screen
for n, (f, (cx, cy, r)) in enumerate(zip(frames, cens)):
    canvas = np.zeros((ch, cw, 4), np.uint8)
    ox, oy = int(round(L - cx)) + 1, int(round(T - cy)) + 1
    canvas[oy:oy + f.shape[0], ox:ox + f.shape[1]] = f
    save(f"bat_{n}", canvas, SW, body=[round((L + 1) / cw, 4), round((T + 1) / ch, 4)])

b = trim(big["img"])
cx, cy, r = body_center(b)
print(f"bat_big {b.shape[1]}x{b.shape[0]} body ({cx:.0f},{cy:.0f}) r {r:.0f}")
save("bat_big", b, None, body=[round(cx / b.shape[1], 4), round(cy / b.shape[0], 4), round(r / b.shape[1], 4)])

# ---------- Pumpkins ----------
pk = pieces(key(Image.open(SRC / "pumpkins.png")), join=9, min_area=300)
pk.sort(key=lambda q: -q["w"] * q["h"])
whole, bits = pk[:6], pk[6:]
H = Image.open(SRC / "pumpkins.png").height
whole.sort(key=lambda q: (q["y"] + q["h"] / 2 > H * .42, q["x"]))   # top row, then bottom row, left to right
for n, q in enumerate(whole):
    p = trim(q["img"])
    solid = (p[..., 3] > 128)
    rows = np.where(solid.any(1))[0]
    body = solid[rows.min() + int(len(rows) * .25):]          # measure the radius from the body width, excluding the stem
    rr = (body.any(0).sum()) / 2
    save(f"pk_{n}", p, 300, r=round(float(rr / p.shape[1]), 4))
    print(f"pk_{n} {p.shape[1]}x{p.shape[0]}")
bits.sort(key=lambda q: q["x"])
print("bits", len(bits))
for n, q in enumerate(bits):
    save(f"pk_bit_{n}", trim(q["img"]), 160)

mf = OUT / "manifest.js"
manifest = json.loads(re.search(r"=\s*(\{.*\})\s*;", mf.read_text(encoding="utf-8"), re.S).group(1))
manifest.update(added)
mf.write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
for k, v in added.items():
    print(k, v["w"], v["h"], (OUT / f"{k}.webp").stat().st_size, v.get("body", v.get("r", "")))
