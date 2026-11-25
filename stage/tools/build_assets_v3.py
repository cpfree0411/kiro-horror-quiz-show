r"""KHQS_v3 (labelled GPT edits) → stage WebP + manifest.js

Plates are fitted to the 1600×900 design coordinates (the stage code's coordinates are based on this size).
Moving pieces are cut out per alpha connected component.
Run: python stage-v3/tools/build_assets_v3.py   (needs Pillow)
"""
import json
import pathlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

STEP = 2


def label(im, thr=40):
    """Alpha connected-component labelling on a reduced grid. (label array, width, height, component list)"""
    a = im.getchannel("A")
    gw, gh = a.width // STEP, a.height // STEP
    small = a.resize((gw, gh), Image.NEAREST).load()
    lab = [0] * (gw * gh)
    comps = []
    for y in range(gh):
        for x in range(gw):
            if lab[y * gw + x] or small[x, y] <= thr:
                continue
            cid = len(comps) + 1
            stack = [(x, y)]
            lab[y * gw + x] = cid
            x0 = x1 = x; y0 = y1 = y; n = 0
            while stack:
                cx, cy = stack.pop(); n += 1
                x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < gw and 0 <= ny < gh and not lab[ny * gw + nx] and small[nx, ny] > thr:
                        lab[ny * gw + nx] = cid; stack.append((nx, ny))
            comps.append({"id": cid, "bbox": (x0 * STEP, y0 * STEP, (x1 + 1) * STEP, (y1 + 1) * STEP), "area": n * STEP * STEP})
    comps = [c for c in comps if c["area"] >= 900]
    comps.sort(key=lambda c: (c["bbox"][1] // 60, c["bbox"][0]))
    return lab, gw, gh, comps

SRC = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets" / "KHQS_v3"
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"
OUT.mkdir(exist_ok=True)
manifest = {}


def save(key, im, max_side=None, quality=86):
    if max_side and max(im.size) > max_side:
        im = im.copy()
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    im.save(OUT / f"{key}.webp", "WEBP", quality=quality, method=6)
    manifest[key] = {"src": f"assets/{key}.webp", "w": im.width, "h": im.height}


def pieces(path, min_area=4000, rows=None):
    """Return the sheet's parts in (top→bottom, left→right) order, cut by component masks. With rows, split into that many rows and sort."""
    im = Image.open(path).convert("RGBA")
    lab, gw, gh, comps = label(im)
    comps = [c for c in comps if c["area"] >= min_area]
    if rows:
        comps.sort(key=lambda c: ((c["bbox"][1] + c["bbox"][3]) // 2 * rows // im.height, c["bbox"][0]))
    out = []
    for c in comps:
        mask = Image.new("L", (gw, gh), 0)
        px = mask.load()
        for i, v in enumerate(lab):
            if v == c["id"]:
                px[i % gw, i // gw] = 255
        mask = mask.filter(ImageFilter.MaxFilter(5)).resize(im.size, Image.NEAREST)
        part = im.crop(c["bbox"])
        part.putalpha(ImageChops.multiply(part.getchannel("A"), mask.crop(c["bbox"])))
        out.append(part.crop(part.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()))
    return out


# Plates: use v4 with the baked English signs if present (same positions as v3)
V4 = SRC.parent / "KHQS_v4"
plates = {}
for act, f in [(1, "1막/act1_plate.png"), (2, "2막/act2_plate.png"), (3, "3막/act3_plate.png")]:
    baked = V4 / f"act{act}_plate_signs.png"
    im = Image.open(baked if baked.exists() else SRC / f).convert("RGB")
    if act == 1 and baked.exists():
        from build_act1_ledges import ledges  # add the act 1 voting ledges (KHQS_v10)
        im = ledges(im)
    im = im.resize((1600, 900), Image.LANCZOS)
    save(f"plate{act}", im, quality=88)
    plates[act] = im

# Character stickers: 4 rows (characters) × 3 columns (idle, cheer, sad). The cheer's effect-line bits are grouped with it.
stickers = pieces(SRC / "1막" / "cast_sheet.png", min_area=8000)
assert len(stickers) == 12, len(stickers)
for r, fan in enumerate(["sack", "tophat_skull", "vampire", "bolt"]):
    for c, pose in enumerate(["idle", "cheer", "sad"]):
        save(f"fan_{fan}_{pose}", stickers[r * 3 + c], 360)

# 8 audience heads + 6 seats
heads = pieces(SRC / "1막" / "audience_heads.png")
assert len(heads) == 8, len(heads)
for i, p in enumerate(heads):
    save(f"aud_{i}", p, 320)
seats = pieces(SRC / "1막" / "audience_seats.png")
assert len(seats) == 6, len(seats)
for i, p in enumerate(seats):
    save(f"seat_{i}", p, 420)

# empty-seat board, BUZZ burst
for key, f, side in [("vacant", "1막/vacant_board.png", 520), ("buzz", "2막/buzz_burst.png", 520)]:
    im = Image.open(SRC / f).convert("RGBA")
    save(key, im.crop(im.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()), side)


# ghost host (KHQS_v5)
def clean_alpha(im):
    """Clean up leftovers from GPT's transparency (very faint smudges, a slightly see-through body)."""
    a = im.getchannel("A").point(lambda v: 0 if v < 16 else 255 if v >= 236 else round((v - 16) * 255 / 220))
    im.putalpha(a)
    return im.crop(a.getbbox())


def erase_face(im):
    """Erase the face of the neutral pose. Fill the dark parts with the surrounding colour; eyes and mouth are drawn by code."""
    w, h = im.size
    rgb = im.convert("RGB")
    gray = rgb.convert("L").load()
    mask = Image.new("L", im.size, 0)
    px = mask.load()
    for y in range(int(h * .22), int(h * .56)):
        for x in range(int(w * .26), int(w * .76)):
            if gray[x, y] < 228:
                px[x, y] = 255
    mask = mask.filter(ImageFilter.MaxFilter(15))
    for _ in range(80):
        rgb.paste(rgb.filter(ImageFilter.GaussianBlur(8)), mask=mask)
    out = rgb.convert("RGBA")
    out.putalpha(im.getchannel("A"))
    return out


def add_highlights(im):
    """Put the same small highlights as the acting sheet into the eyes of the expression sheet. Only tall dark blobs near the top count as eyes."""
    w, h = im.size
    gray = im.convert("L").load()
    alpha = im.getchannel("A").load()
    seen, eyes = set(), []
    for y in range(int(h * .15), int(h * .42)):
        for x in range(w):
            if (x, y) in seen or gray[x, y] > 70 or alpha[x, y] < 200:
                continue
            st, cur = [(x, y)], []
            seen.add((x, y))
            while st:
                a, b = st.pop(); cur.append((a, b))
                for c, d in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                    if 0 <= c < w and 0 <= d < h and (c, d) not in seen and gray[c, d] <= 70:
                        seen.add((c, d)); st.append((c, d))
            xs, ys = [p[0] for p in cur], [p[1] for p in cur]
            bw, bh = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            if len(cur) > 250 and bh > bw * 1.25 and (min(ys) + max(ys)) / 2 < h * .42:
                eyes.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, bw / 2, bh / 2))
    S = 4
    dots = Image.new("L", (w * S, h * S), 0)
    draw = ImageDraw.Draw(dots)
    for ex, ey, rx, ry in eyes:
        dx, dy, r = ex + rx * .3, ey - ry * .36, rx * .2
        draw.ellipse([(dx - r) * S, (dy - r) * S, (dx + r) * S, (dy + r) * S], fill=255)
    out = im.copy()
    out.paste((255, 255, 255, 255), mask=dots.resize(im.size, Image.LANCZOS))
    return out, len(eyes)


def anchor_x(im):
    """The centre near the top of the head. A reference point that does not move when arms stretch, so the body does not jump when the expression changes."""
    a = im.getchannel("A").load()
    y = int(im.height * .15)
    xs = [x for x in range(im.width) if a[x, y] > 128]
    return (min(xs) + max(xs)) / 2


def stage_grade(im):
    """Colour grade that puts the ghost into the stage: warm light, gold rim at top left, red bounce from the curtain, lectern shadow, paper texture, thin ink outline."""
    im = ImageOps.expand(im, 3, (0, 0, 0, 0))
    a = im.getchannel("A")
    w, h = im.size
    rgb = ImageChops.multiply(im.convert("RGB"), Image.new("RGB", im.size, (255, 236, 212)))

    def tint(color, mask):
        rgb.paste(Image.new("RGB", im.size, color), mask=mask)

    key = ImageChops.subtract(a, ImageChops.offset(a, 6, 7)).filter(ImageFilter.GaussianBlur(3))
    tint((255, 198, 120), key.point(lambda v: round(v * .5)))
    bounce = ImageChops.subtract(a, ImageChops.offset(a, -8, -4)).filter(ImageFilter.GaussianBlur(5))
    tint((206, 52, 56), bounce.point(lambda v: round(v * .5)))
    shade = Image.linear_gradient("L").resize(im.size).point(lambda v: round(max(0, v - 165) * 1.5))  # darken only the bottom
    tint((86, 34, 58), ImageChops.multiply(shade, a))
    noise = Image.effect_noise((w // 2 + 1, h // 2 + 1), 34).resize(im.size, Image.BILINEAR).convert("RGB")
    rgb = Image.blend(rgb, ImageChops.overlay(rgb, noise), .22)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    ink = Image.new("RGBA", im.size, (44, 20, 30, 0))
    ink.putalpha(a.filter(ImageFilter.MaxFilter(5)).point(lambda v: round(v * .85)))
    ink.alpha_composite(out)
    return ink


def save_front(act, poly, mics=()):
    """Cut the lectern and mic out of the plate. Laid over the ghost so it seems to stand behind the lectern."""
    S = 4
    mask = Image.new("L", (1600 * S, 900 * S), 0)
    draw = ImageDraw.Draw(mask)
    for p in (poly, *mics):
        draw.polygon([(x * S, y * S) for x, y in p], fill=255)
    mask = mask.resize((1600, 900), Image.LANCZOS)
    box = mask.getbbox()
    part = plates[act].convert("RGBA")
    part.putalpha(mask)
    save(f"front{act}", part.crop(box), quality=92)
    manifest[f"front{act}"].update(x=box[0], y=box[1])


save_front(1, [(96, 626), (167, 615), (301, 619), (302, 666), (96, 666)],
           [[(270, 549), (284, 556), (287, 571), (279, 590), (271, 597), (267, 601), (266, 612), (278, 620), (245, 620), (253, 612), (254, 598), (249, 590), (246, 575), (251, 562), (260, 551)]])
save_front(2, [(58, 540), (104, 531), (106, 522), (161, 522), (165, 528), (206, 528), (211, 537), (245, 543), (245, 586), (58, 586)],
           [[(155, 457), (163, 447), (178, 451), (193, 473), (191, 486), (184, 491), (188, 503), (187, 530), (176, 530), (176, 500), (171, 484), (157, 470)]])
save_front(3, [(83, 599), (188, 586), (347, 598), (347, 642), (83, 642)])


V5 = SRC.parent / "KHQS_v5"
faces = [clean_alpha(p) for p in pieces(V5 / "ghost_faces.png", min_area=20000, rows=3)]
assert len(faces) == 9, len(faces)
acting = [clean_alpha(p) for p in pieces(V5 / "ghost_acting.png.png", min_area=20000)]
assert len(acting) == 3, len(acting)
acting = [p.resize((round(p.width * .55), round(p.height * .55)), Image.LANCZOS) for p in acting]  # match the height to the expression sheet
def save_ghost(key, p):
    p = stage_grade(p)
    save(f"ghost_{key}", p)
    manifest[f"ghost_{key}"]["ax"] = anchor_x(p)


save_ghost("body", erase_face(faces[0]))
for key, p in zip(["happy", "surprised", "worried", "wink", "sad", "angry", "sleep", "present"], faces[1:]):
    p, n = add_highlights(p)
    print("ghost", key, p.size, "eyes", n)
    save_ghost(key, p)
for key, p in zip(["peek", "think", "tease"], acting):
    print("ghost", key, p.size)
    save_ghost(key, p)



(OUT / "manifest.js").write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
total = sum((OUT / f"{k}.webp").stat().st_size for k in manifest)
print(f"{len(manifest)} assets, {total / 1e6:.2f} MB")
for k in ("plate1", "fan_sack_idle", "fan_bolt_cheer", "aud_0", "seat_0", "ghost_body", "vacant", "buzz"):
    print(k, manifest[k]["w"], manifest[k]["h"])
