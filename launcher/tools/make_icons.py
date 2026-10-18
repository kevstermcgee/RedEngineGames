#!/usr/bin/env python3
"""Draws the launcher's icon (a play button on the site's red) into app/icons: `python3 launcher/tools/make_icons.py` (needs Pillow)."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "icons"
N = 1024


def master() -> Image.Image:
    top, bottom = (0xFF, 0x5C, 0x7A), (0x9E, 0x1F, 0x45)
    grad = Image.new("RGB", (N, N))
    d = ImageDraw.Draw(grad)
    for y in range(N):
        t = y / (N - 1)
        d.line([(0, y), (N, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, N - 40, N - 40], radius=210, fill=255)
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # A dark disc with a play triangle: "press play".
    c, r = N // 2, 300
    d.ellipse([c - r, c - r, c + r, c + r], fill=(0x16, 0x0B, 0x13, 255))
    s = 150
    d.polygon([(c - s * 0.75, c - s), (c - s * 0.75, c + s), (c + s * 1.05, c)], fill=(0xFF, 0x5C, 0x7A, 255))
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    big = master()
    for name, size in (("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256), ("icon.png", 512)):
        big.resize((size, size), Image.LANCZOS).save(OUT / name)
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
