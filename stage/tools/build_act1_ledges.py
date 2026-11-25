r"""Act 1 voting ledges (KHQS_v10) → rewrites plate1.webp

On the existing act 1 plate (v4, with baked sign text) only the small name-tag area under the O and X cards is replaced by the wide ledge from the new art.
Everything else is the existing art. When picks are revealed, players rise from behind this ledge ("Act 1 voting ledges" in stage.js).

Run: python stage-v3/tools/build_act1_ledges.py   (needs Pillow)
build_assets_v3.py does the same composite (ledges()), so rebuilding everything keeps the ledges.
"""
import pathlib

from PIL import Image, ImageDraw, ImageFilter

ART = pathlib.Path.home() / "Desktop" / "대화용 임시저장" / "작업용 스샷" / "kiro-assets"
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"
BOX = (404, 671, 1286, 768)                           # the two ledges and the space between (original 1672×941 coordinates)


def ledges(base):
    """Return the v4 plate with the v10 ledges on it. Without the v10 art, return it unchanged."""
    src = ART / "KHQS_v10" / "act1_plate_ledges.png"
    if not src.exists():
        return base
    new = Image.open(src).convert("RGB").resize(base.size, Image.LANCZOS)
    blend = Image.new("L", base.size, 0)
    ImageDraw.Draw(blend).rectangle(BOX, fill=255)
    return Image.composite(new, base, blend.filter(ImageFilter.GaussianBlur(4)))


if __name__ == "__main__":
    base = Image.open(ART / "KHQS_v4" / "act1_plate_signs.png").convert("RGB")
    plate = ledges(base).resize((1600, 900), Image.LANCZOS)
    plate.save(OUT / "plate1.webp", "WEBP", quality=88, method=6)
    print("plate1", (OUT / "plate1.webp").stat().st_size)
