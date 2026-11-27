"""Render the SmartPlate home-screen icons from app/static/assets/app-icon.svg.

Pillow cannot read SVG, so the same shapes are redrawn here with the identical
coordinates. Keep this in step with the SVG if the mark ever changes.

Everything is drawn at 4x and scaled down, which is what gives the circles and
the spark clean edges.

    python tools/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "icons"
CANVAS = 512          # the SVG's own coordinate space
SCALE = 4             # supersample, then downscale
SIZES = {"icon-512.png": 512, "icon-192.png": 192, "icon-180.png": 180}

SAGE = "#4FA07E"
WHITE = "#FFFFFF"
MINT = "#EAF7F0"
AMBER = "#F6C66B"


def s(v: float) -> float:
    return v * SCALE


def ring(draw, cx, cy, r, colour, width):
    draw.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)],
                 outline=colour, width=int(s(width)))


def tilted_ellipse(img, cx, cy, rx, ry, angle, colour):
    """A rotated ellipse, drawn on its own layer so it can be turned."""
    pad = int(s(max(rx, ry)) * 2) + 8
    layer = Image.new("RGBA", (pad, pad), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    mid = pad / 2
    ld.ellipse([mid - s(rx), mid - s(ry), mid + s(rx), mid + s(ry)], fill=colour)
    layer = layer.rotate(angle, resample=Image.BICUBIC)
    img.alpha_composite(layer, (int(s(cx) - mid), int(s(cy) - mid)))


def build() -> Image.Image:
    size = int(s(CANVAS))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(s(115)), fill=SAGE)
    ring(draw, 256, 266, 170, WHITE, 20)
    ring(draw, 256, 266, 104, WHITE, 13)

    # The stem, with round caps drawn as discs at each end.
    draw.line([s(256), s(232), s(256), s(322)], fill=WHITE, width=int(s(14)))
    for y in (232, 322):
        draw.ellipse([s(256 - 7), s(y - 7), s(256 + 7), s(y + 7)], fill=WHITE)

    # Two leaves. Pillow rotates counter-clockwise, SVG clockwise, so the
    # angles are negated.
    tilted_ellipse(img, 220, 250, 36, 20, 35, WHITE)
    tilted_ellipse(img, 292, 238, 36, 20, -35, MINT)

    star = [(392, 96), (404, 138), (446, 150), (404, 162),
            (392, 204), (380, 162), (338, 150), (380, 138)]
    draw.polygon([(s(x), s(y)) for x, y in star], fill=AMBER)
    return img


def main() -> None:
    master = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, px in SIZES.items():
        master.resize((px, px), Image.LANCZOS).save(OUT_DIR / name)
        print(f"wrote {OUT_DIR / name} ({px}x{px})")


if __name__ == "__main__":
    main()
