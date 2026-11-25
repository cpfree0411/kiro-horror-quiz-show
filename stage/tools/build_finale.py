r"""Finale (KHQS_v9) → plateF, frontF, fin_pod1~3, fin_trophy, fin_crown, fin_rosette, fin_theend, fin_bouquet + manifest.js entries

plateF : the stage with the boards cleared and the curtain closed. The ON AIR and APPLAUSE lettering comes from the existing act 3 plate (v4).
frontF : the host lectern cut out of plateF (same spot as front3, laid over the ghost).
fin_pod: three podiums. The manifest records the front paper plaque's position (plaque, fraction of the art size).
props  : trophy, crown, rosette, THE END sign, bouquet.

Run: python stage-v3/tools/build_finale.py   (needs Pillow, numpy, opencv)
Rerunning build_assets_v3.py rewrites manifest.js, so rerun this file after it.
"""
import json
import pathlib
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ART = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets"
SRC = ART / "KHQS_v9"
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"
added = {}


def save(key, im, max_side=None, quality=90, **extra):
    if max_side and max(im.size) > max_side:
        im = im.copy()
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    im.save(OUT / f"{key}.webp", "WEBP", quality=quality, method=6)
    added[key] = {"src": f"assets/{key}.webp", "w": im.width, "h": im.height, **extra}
    return im


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


def pieces(path, count, min_area=6000, pad=3):
    """Cut pieces from a blue-background sheet in order from the left. Each piece keeps only its own blob."""
    rgba = key(Image.open(path))
    solid = (rgba[..., 3] > 40).astype(np.uint8)
    solid = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid)
    comps = sorted((i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area), key=lambda i: stats[i, cv2.CC_STAT_LEFT])
    assert len(comps) == count, (path.name, len(comps), count)
    out = []
    for i in comps:
        x, y, w, h = stats[i, :4]
        x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(rgba.shape[1], x + w + pad), min(rgba.shape[0], y + h + pad)
        part = rgba[y0:y1, x0:x1].copy()
        own = cv2.dilate((lab[y0:y1, x0:x1] == i).astype(np.uint8), np.ones((5, 5), np.uint8))
        part[..., 3] = part[..., 3] * own
        out.append(Image.fromarray(part, "RGBA"))
    return out


# ── Stage ──
base = Image.open(ART / "KHQS_v4" / "act3_plate_signs.png").convert("RGB")
stage = Image.open(SRC / "finale_stage.png").convert("RGB").resize(base.size, Image.LANCZOS)
blend = Image.new("L", base.size, 0)
for box in [(52, 30, 330, 196), (1362, 34, 1626, 190)]:      # ON AIR, APPLAUSE signs (lettering baked in)
    ImageDraw.Draw(blend).rounded_rectangle(box, 18, fill=255)
blend = blend.filter(ImageFilter.GaussianBlur(7))
plate = Image.composite(base, stage, blend).resize((1600, 900), Image.LANCZOS)
save("plateF", plate, quality=88)

# host lectern: the same polygon as front3
S = 4
mask = Image.new("L", (1600 * S, 900 * S), 0)
ImageDraw.Draw(mask).polygon([(x * S, y * S) for x, y in [(83, 599), (188, 586), (347, 598), (347, 642), (83, 642)]], fill=255)
mask = mask.resize((1600, 900), Image.LANCZOS)
box = mask.getbbox()
front = plate.convert("RGBA")
front.putalpha(mask)
save("frontF", front.crop(box), quality=92, x=box[0], y=box[1])

def tall_pod3(im, extra=.09):
    """The 3rd-place podium is short, so its name plaque is flat (the name text was small in the demo). Stretch the body under the number disc vertically to enlarge the plaque.
    The middle (vertical wood grain, paper plaque) is stretched; the riveted side borders repeat a rivet-free stretch so the rivets are not squashed.
    Coordinates are fractions of the art size (for 420x370: stretch band y 200–280, inside the border x 52–368, rivet-free stretch y 250–278)."""
    a = np.asarray(im)
    H, W = a.shape[:2]
    y0, y1, add = round(.54 * H), round(.757 * H), round(extra * H)
    p0, p1 = round(.676 * H), round(.751 * H)          # the rivet-free rows in the side border
    xl, xr = round(.124 * W), round(.876 * W)
    mid = np.asarray(Image.fromarray(a[y0:y1, xl:xr]).resize((xr - xl, y1 - y0 + add), Image.LANCZOS))
    plain = a[p0:p1]
    reps = -(-add // len(plain))
    filler = np.concatenate([plain] * reps)[:add]
    side = np.concatenate([a[y0:p1], filler, a[p1:y1]])   # repeat the rivet-free rows after themselves
    band = side.copy()
    band[:, xl:xr] = mid
    return Image.fromarray(np.concatenate([a[:y0], band, a[y1:]]), "RGBA")


# ── Podiums: from the left 2nd, 1st, 3rd ──
for rank, im in zip((2, 1, 3), pieces(SRC / "finale_podiums.png", 3)):
    if rank == 3:
        im = tall_pod3(im)
    a = np.asarray(im).astype(int)
    r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    cream = ((r > 215) & (g > 185) & (b > 120) & (b < 215) & (al > 200)).astype(np.uint8)
    cream[: int(im.height * (.42 if rank == 3 else .45))] = 0   # leave out the number disc at the top (the stretched 3rd place's plaque starts a little higher)
    cream = cv2.morphologyEx(cream, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cream)
    big = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])
    x, y, w, h = stats[big, :4]
    plaque = [round(float(v), 4) for v in (x / im.width, y / im.height, (x + w) / im.width, (y + h) / im.height)]
    save(f"fin_pod{rank}", im, 440 if rank == 1 else 420, plaque=plaque)

# ── Props ──
for name, im, side in zip(("trophy", "crown", "rosette", "theend", "bouquet"), pieces(SRC / "finale_props.png", 5), (300, 240, 220, 620, 260)):
    save(f"fin_{name}", im, side)

mf = OUT / "manifest.js"
manifest = json.loads(re.search(r"=\s*(\{.*\})\s*;", mf.read_text(encoding="utf-8"), re.S).group(1))
manifest.update(added)
mf.write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
for k, v in added.items():
    print(k, v["w"], v["h"], (OUT / f"{k}.webp").stat().st_size, v.get("plaque", ""))
