#!/usr/bin/env python3
"""Render the PNG fallbacks for static/favicon.svg with Pillow.

The site ships an SVG favicon plus two raster fallbacks (32 px tab icon and
180 px apple-touch-icon). No SVG rasteriser is available on the build
machine, so the tiles are redrawn here with the same geometry as the SVG:
a #c8252c rounded square with the kanji 漢 in white, centred on its ink box.

The glyph comes from the system Noto Sans CJK JP Bold (no font is embedded
in the site). Pass --font to use a different TTC/TTF.

Usage:
    python3 make_favicon.py
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
STATIC = BASE_DIR / "static"
GLYPH = "漢"
BG = "#c8252c"
FG = "#ffffff"
# Matches the SVG: 48 px glyph in a 64 px tile, 14 px corner radius.
GLYPH_RATIO = 48 / 64
RADIUS_RATIO = 14 / 64
SUPERSAMPLE = 4
DEFAULT_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
# Index 0 of NotoSansCJK-Bold.ttc is "Noto Sans CJK JP".
DEFAULT_FONT_INDEX = 0

TARGETS = (("favicon-32.png", 32), ("apple-touch-icon.png", 180))


def render(size, font_path, font_index):
    """Return one RGBA tile of `size` px."""
    scale = size * SUPERSAMPLE
    img = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = round(scale * RADIUS_RATIO)
    draw.rounded_rectangle((0, 0, scale - 1, scale - 1), radius=radius, fill=BG)

    font = ImageFont.truetype(font_path, round(scale * GLYPH_RATIO),
                             index=font_index)
    # Centre the glyph on its actual ink box, not on the em box, so it sits
    # optically centred in the tile at 16 px.
    x0, y0, x1, y1 = font.getbbox(GLYPH)
    cx = cy = scale / 2
    tx = cx - (x0 + x1) / 2
    ty = cy - (y0 + y1) / 2
    draw.text((tx, ty), GLYPH, font=font, fill=FG, anchor="la")

    return img.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--font", default=DEFAULT_FONT)
    ap.add_argument("--font-index", type=int, default=DEFAULT_FONT_INDEX)
    args = ap.parse_args()

    if not Path(args.font).exists():
        raise SystemExit(f"font not found: {args.font} (pass --font)")

    for name, size in TARGETS:
        out = STATIC / name
        render(size, args.font, args.font_index).save(out, optimize=True)
        print(f"wrote {out.relative_to(BASE_DIR)} ({size}x{size})")


if __name__ == "__main__":
    main()
