r"""Cast-board lobby (KHQS_v12) → lobby, lobby_dark, lobby_cards (+ showtime_off, showtime_on) + manifest.js entries

lobby       : lobby background (1600×900). The QR slot is blank paper; the three cards are "?" silhouettes.
lobby_dark  : the same background with the power out. Used for bulb flicker (around a bulb only) and the blackout (everything).
lobby_cards : a strip with three blank cards (silhouettes removed). The base of registered cards.
showtime_*  : the IT'S SHOWTIME! sign unlit and lit (same size).

If the art received in the KHQS_v12 folder exists, use it. Otherwise make temporary art from a copy of the concept image
(QR and silhouettes filled with the surrounding paper; the unlit background darkened. Temporary, so rough up close).

Run: python stage-v3/tools/build_cast_lobby.py [concept image path]   (needs Pillow, numpy, opencv)
Rerunning build_assets_v3.py rewrites manifest.js, so rerun this file after it.
"""
import json
import pathlib
import re
import sys

import cv2
import numpy as np
from PIL import Image

SRC = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets" / "KHQS_v12"
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"
W, H = 1600, 900

# Stage coordinates (1600×900). Must match CAST in stage.js
QR = (325, 433, 528, 632)                      # QR slot to fill
CARDS = [(681, 342, 922, 667), (953, 342, 1196, 667), (1226, 342, 1467, 667)]
STRIP = (670, 334, 1478, 676)                  # area covered by the blank-card strip
CANDLES = [(155, 598, 36, 617), (95, 552, 42, 573)]   # candle flames (x, y, erase radius, wax-top y). Erase the flame and the glow around it
SNUFF_BOX = (40, 470, 230, 680)                # area cut out as lobby_snuff
GLOWS = [(96, 560, 70), (155, 612, 60), (254, 756, 120), (1522, 756, 150)]   # lights that stay when the power goes: two candles, lantern, pumpkin


def load(name):
    for p in sorted(SRC.glob(name + ".*")) if SRC.exists() else []:
        return np.asarray(Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS))
    return None


def paper_fill(a, mask):
    """Fill the mask area with the surrounding paper (temporary). Add a little paper grain over the smeared fill."""
    m = cv2.dilate(mask.astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
    bgr = cv2.inpaint(cv2.cvtColor(a, cv2.COLOR_RGB2BGR), m, 9, cv2.INPAINT_TELEA)
    out = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    rng = np.random.default_rng(7)
    grain = cv2.GaussianBlur(rng.normal(0, 1, a.shape[:2]).astype(np.float32), (0, 0), 1.6) * 9
    out += (grain * (m > 0))[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


plate, blank, dark = load("lobby_plate"), load("lobby_plate_blank"), load("lobby_plate_dark")
temp = []
if plate is None:
    concept = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    assert concept and concept.exists(), "without KHQS_v12/lobby_plate, pass a concept image path as the argument"
    a = np.asarray(Image.open(concept).convert("RGB").resize((W, H), Image.LANCZOS))
    m = np.zeros((H, W), bool)
    m[QR[1]:QR[3], QR[0]:QR[2]] = True
    plate = paper_fill(a, m)
    temp.append("lobby")
if blank is None:
    lum = plate.astype(np.float32) @ np.array([.299, .587, .114], np.float32)
    m = np.zeros((H, W), bool)
    for x0, y0, x1, y1 in CARDS:                # silhouettes and emphasis lines: the dark areas inside the portrait slots
        box = np.zeros((H, W), bool)
        box[y0 + 40:y0 + 222, x0 + 24:x1 - 24] = True
        m |= box & (lum < 150)
    blank = paper_fill(plate, m)
    temp.append("lobby_cards")
if dark is None:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    keep = np.full((H, W), .13, np.float32)
    for gx, gy, r in GLOWS:
        keep = np.maximum(keep, .13 + .8 * np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / (2 * r * r)))
    d = plate.astype(np.float32)
    hot = np.clip((d.max(2) - 200) / 55, 0, 1)[..., None]              # lit bulbs become grey glass
    near = cv2.GaussianBlur(hot[..., 0], (0, 0), 14)[..., None]         # around a bulb is less dark, so one dead bulb does not look like a black hole
    d = d * keep[..., None] * (1 + 2.2 * np.clip(near * 3, 0, 1)) * np.array([1, .93, .9], np.float32)
    d = d * (1 - hot) + np.array([86, 76, 64], np.float32) * hot        # dead bulbs: murky glass
    dark = np.clip(d, 0, 255).astype(np.uint8)
    temp.append("lobby_dark")
else:
    # The received art must differ only in lighting, with objects in place. Report it here if misaligned
    e1 = cv2.Canny(cv2.cvtColor(plate, cv2.COLOR_RGB2GRAY), 60, 160)
    e2 = cv2.Canny(cv2.cvtColor(dark, cv2.COLOR_RGB2GRAY), 30, 90)
    (dx, dy), _ = cv2.phaseCorrelate(e1.astype(np.float32), e2.astype(np.float32))
    print(f"lobby_dark misaligned: x {dx:+.1f}px, y {dy:+.1f}px")

added = {}


def save(name, arr, **extra):
    im = Image.fromarray(arr)
    im.save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)
    added[name] = {"src": f"assets/{name}.webp", "w": im.width, "h": im.height, **extra}


save("lobby", plate)
save("lobby_dark", dark)
off = load("lobby_plate_off")                  # background with every light out (if present): used as the candles, lantern and pumpkin go out one by one
if off is not None:
    save("lobby_off", off)
    # lobby_snuff: a patch around the candles with only the flames erased. When one candle goes out the room is still bright in its neighbours' light,
    # so covering the dead candle with the dark background would leave a black hole. Cover it with this patch: brightness unchanged, flame erased
    sx0, sy0, sx1, sy1 = SNUFF_BOX
    d = dark.copy()
    lum = d.astype(np.float32) @ np.array([.299, .587, .114], np.float32)
    m = np.zeros((H, W), np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    for fx, fy, fr, wax in CANDLES:            # only above the wax: the candle body stays lit by the neighbouring light
        m |= (((xx - fx) ** 2 + (yy - fy) ** 2 < fr * fr) & (yy < wax) & (lum > 70)).astype(np.uint8)
    m = cv2.dilate(m, np.ones((9, 9), np.uint8)) & (yy < np.where(xx < 125, 573, 617)).astype(np.uint8)
    bgr = cv2.inpaint(cv2.cvtColor(d, cv2.COLOR_RGB2BGR), m * 255, 15, cv2.INPAINT_TELEA)
    snuff = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)[sy0:sy1, sx0:sx1]
    save("lobby_snuff", np.ascontiguousarray(snuff), x=sx0, y=sy0)
    print("snuff pixels erased", int(m.sum()))
x0, y0, x1, y1 = STRIP
save("lobby_cards", blank[y0:y1, x0:x1], x=x0, y=y0)

# Sign: unlit (top) and lit (bottom) on one sheet with a blue background
sign = next(iter(sorted(SRC.glob("showtime_sign.*"))), None) if SRC.exists() else None
if sign:
    s = np.asarray(Image.open(sign).convert("RGB")).astype(np.float32)
    r, g, b = s[..., 0], s[..., 1], s[..., 2]
    strict = (b > 130) & (b - r > 70) & (b - g > 35) & (g > r + 15)
    bg = s[strict].mean(0)
    bb = np.maximum(b, 1.0)
    c = np.abs(r / bb - bg[0] / bg[2]) + np.abs(g / bb - bg[1] / bg[2])
    alpha = np.clip((c - .10) / .30, 0, 1)
    alpha[alpha < .04] = 0
    al = np.maximum(alpha, .05)[..., None]
    fg = np.where(alpha[..., None] >= .999, s, np.clip((s - (1 - alpha[..., None]) * bg) / al, 0, 255))
    rgba = np.dstack([fg, alpha * 255]).astype(np.uint8)
    half = rgba.shape[0] // 2
    boxes = []
    for part in (rgba[:half], rgba[half:]):
        solid = cv2.morphologyEx((part[..., 3] > 40).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        ys, xs = np.where(solid)
        boxes.append((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    bw, bh = max(b[2] - b[0] for b in boxes), max(b[3] - b[1] for b in boxes)   # both the same size, aligned at the bottom centre
    for name, part, (bx0, by0, bx1, by1) in zip(("showtime_off", "showtime_on"), (rgba[:half], rgba[half:]), boxes):
        cx = (bx0 + bx1) // 2
        im = Image.new("RGBA", (bw, bh))
        crop = Image.fromarray(part[by1 - bh if by1 - bh >= 0 else 0:by1, max(0, cx - bw // 2):cx - bw // 2 + bw], "RGBA")
        im.paste(crop, (0, bh - crop.height))
        if bw > 900:
            im = im.resize((900, round(bh * 900 / bw)), Image.LANCZOS)
        im.save(OUT / f"{name}.webp", "WEBP", quality=90, method=6)
        added[name] = {"src": f"assets/{name}.webp", "w": im.width, "h": im.height}

mf = OUT / "manifest.js"
manifest = json.loads(re.search(r"=\s*(\{.*\})\s*;", mf.read_text(encoding="utf-8"), re.S).group(1))
manifest.update(added)
mf.write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
for k, v in added.items():
    print(k, v["w"], v["h"], (OUT / f"{k}.webp").stat().st_size, "(temporary)" if k in temp else "")
