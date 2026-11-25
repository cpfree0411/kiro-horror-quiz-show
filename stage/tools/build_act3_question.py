r"""Act 3 last question board (KHQS_v17, red tin frame without bulbs) → plate3q.webp, qboard3.webp, two entries in manifest.js

plate3q : the existing act 3 plate (v4, with baked sign text) with the new question board hung on it. Scoreboards, clock, lectern and sign are the existing art.
qboard3 : the question board alone (crown and chains included) cut from plate3q. Used for the drop-in motion.
          When fully down it matches the same spot in plate3q pixel for pixel. The manifest records where it goes (x, y).

The GPT-drawn scene (act3_question_scene.png) redrew the scoreboards 12 px lower, so the board is that much lower too.
The existing scoreboards are kept, so only the board is raised 12 px (DY) to hang just above the scoreboards like the original board.
The tools and art of the previous version (KHQS_v8, bulb marquee) are in review/act3-board-v8-backup/.

Run: python stage-v3/tools/build_act3_question.py   (needs Pillow, numpy, opencv)
Rerunning build_assets_v3.py rewrites manifest.js, so rerun this file after it.
"""
import json
import pathlib
import re

import cv2
import numpy as np
from PIL import Image, ImageFilter

ART = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets"
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"
DY = -12                                             # how far to raise the board (1672×941 space)

base = Image.open(ART / "KHQS_v4" / "act3_plate_signs.png").convert("RGB")
scene = Image.open(ART / "KHQS_v17" / "act3_question_scene.png").convert("RGB").resize(base.size, Image.LANCZOS)
assert base.size == (1672, 941), base.size
sc = np.array(scene)

# 1. The board's shape. Board and frame are bright; the curtain behind is dark
hsv = cv2.cvtColor(sc, cv2.COLOR_RGB2HSV)
hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
lit = (val > 85).astype(np.uint8)
lit[:, :366] = 0
lit[:, 1305:] = 0
lit[532:] = 0
lit = cv2.morphologyEx(lit, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def largest(m):
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    return (lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)


body = lit.copy()
body[:95] = 0                                        # body (the square board)
body = largest(cv2.morphologyEx(body, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))))
crest = lit.copy()                                   # the arch and ornaments on top. Leave out the red valance at the very top (y<44); only the crown area reaches higher
crest[100:] = 0
crest[:44, :775] = 0
crest[:44, 895:] = 0
crest[:8] = 0
crest[:, :400] = 0
crest[:, 1270:] = 0
crest = cv2.morphologyEx(crest, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
mask = largest(cv2.morphologyEx(body | crest, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))))
hole = (1 - mask).astype(np.uint8)
cv2.floodFill(hole, None, (0, 0), 0)
mask |= hole                                         # fill the inner holes
gold = ((hue >= 8) & (hue <= 35) & (sat > 70) & (val > 60)).astype(np.uint8)
for x0, x1 in ((498, 515), (1158, 1175)):            # the two chains
    mask[0:110, x0:x1] |= gold[0:110, x0:x1]
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
mask[:127, 1268:] = 0                                # the star hanging against the top right corner (left on the stage side)
mask[:134, 1277:] = 0
mask[:137, 1284:] = 0

# 2. Raise the board by DY
moved = np.zeros_like(sc)
moved_mask = np.zeros_like(mask)
moved[:DY] = sc[-DY:]
moved_mask[:DY] = mask[-DY:]

# 3. Plate: the existing art + the GPT scene's curtain at the top centre (erases the old FINAL BET sign).
#    The edge of the original board left after raising (a few pixels at the bottom edge) is filled from the existing art
X0, X1, Y1 = 345, 1340, 508
blend = Image.new("L", base.size, 0)
blend.paste(255, (X0, 0, X1, Y1))
blend = blend.filter(ImageFilter.GaussianBlur(6))
blend.paste(255, (X0 + 14, 0, X1 - 14, 12))
back = np.array(Image.composite(scene, base, blend))
left = (mask == 1) & (moved_mask == 0)
back[left] = np.array(base)[left]
alpha = Image.fromarray(moved_mask * 255).filter(ImageFilter.GaussianBlur(1.0))
a = np.asarray(alpha, np.float32)[..., None] / 255
plate = Image.fromarray((moved * a + back * (1 - a)).round().astype(np.uint8))

# 4. Shrink to stage coordinates (1600×900) and save
plate = plate.resize((1600, 900), Image.LANCZOS)
alpha = alpha.resize((1600, 900), Image.LANCZOS)
box = alpha.point(lambda v: 255 if v > 16 else 0).getbbox()
piece = plate.convert("RGBA")
piece.putalpha(alpha)
piece = piece.crop(box)
plate.save(OUT / "plate3q.webp", "WEBP", quality=88, method=6)
piece.save(OUT / "qboard3.webp", "WEBP", quality=92, method=6)

mf = OUT / "manifest.js"
manifest = json.loads(re.search(r"=\s*(\{.*\})\s*;", mf.read_text(encoding="utf-8"), re.S).group(1))
manifest["plate3q"] = {"src": "assets/plate3q.webp", "w": plate.width, "h": plate.height}
manifest["qboard3"] = {"src": "assets/qboard3.webp", "w": piece.width, "h": piece.height, "x": box[0], "y": box[1]}
mf.write_text("window.KHQS_ASSETS = " + json.dumps(manifest, ensure_ascii=False) + ";\n", encoding="utf-8")
print("plate3q", (OUT / "plate3q.webp").stat().st_size, "qboard3", (OUT / "qboard3.webp").stat().st_size, "box", box)
