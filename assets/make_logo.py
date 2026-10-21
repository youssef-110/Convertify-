"""Draws the Convertify logo (a "C" that is also a convert arrow) and writes every icon size the app uses.

Run from the project folder:  .venv\\Scripts\\python.exe assets\\make_logo.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

INK, LIME, MIST = "#12151C", "#C6F432", "#F4F6F0"
HERE = Path(__file__).parent
S = 2048  # drawn large, then scaled down for smooth edges


def tile(size):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.23), fill=INK)
    cx, cy = S * 0.46, S / 2  # nudged left: the open side carries less visual weight
    r, w = S * 0.30, S * 0.115
    start, end = 50, 320  # the C opens on the right; degrees, clockwise from 3 o'clock
    color = LIME
    d.arc((cx - r, cy - r, cx + r, cy + r), start, end, fill=color, width=int(w))
    # round cap where the C starts
    a = math.radians(start)
    px, py = cx + (r - w / 2) * math.cos(a), cy + (r - w / 2) * math.sin(a)
    d.ellipse((px - w / 2, py - w / 2, px + w / 2, py + w / 2), fill=color)
    # arrowhead at the other end, pointing along the arc into the opening
    a = math.radians(end)
    mid = r - w / 2
    tip_len, half = w * 1.0, w * 0.92
    bx, by = cx + mid * math.cos(a), cy + mid * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)  # clockwise tangent
    nx, ny = math.cos(a), math.sin(a)
    d.polygon([(bx + nx * half, by + ny * half), (bx - nx * half, by - ny * half),
               (bx + tx * tip_len, by + ty * tip_len)], fill=color)
    # the converted "file" the arrow lands on
    f = w * 0.95
    fx, fy = cx + r - w / 2, cy + w * 0.35
    d.rounded_rectangle((fx - f / 2, fy - f / 2, fx + f / 2, fy + f / 2), radius=int(f * 0.28), fill=MIST)
    return im.resize((size, size), Image.LANCZOS)


def main():
    assets, docs = HERE, HERE.parent / "docs"
    docs.mkdir(exist_ok=True)
    tile(256).save(assets / "icon.png")
    tile(512).save(docs / "logo.png")
    tile(150).save(assets / "Square150x150Logo.png")
    tile(44).save(assets / "Square44x44Logo.png")
    tile(50).save(assets / "StoreLogo.png")
    big = tile(256)
    big.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
