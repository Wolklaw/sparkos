"""Draw the Spark Camera icon: a camera (body, top, lens) on a dark tile, with the magenta and
cyan channels slipping out of register behind the mint mark.

Writes icons/spark-camera.svg and icons/spark-camera-<size>.png (16-512 px). Each PNG is drawn at
its own size from the same 32-unit grid as the SVG (and as Mark in sparkcamera/widgets.py).

Run:  python files/spark-camera/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
BODY = (5.5, 10.5, 26.5, 25.5)
TOP = (11.5, 7, 17.5, 10.5)
LENS = (16, 18, 4.6)                  # centre x, centre y, radius
LINE_W = 1.6
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        x0, y0, x1, y1 = BODY
        tx0, ty0, tx1, ty1 = TOP
        cx, cy, r = LENS
        return '\n'.join([
            f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
            f'fill="none" stroke="{colour}" stroke-width="{LINE_W:g}"/>',
            f'  <rect x="{tx0 + dx:g}" y="{ty0:g}" width="{tx1 - tx0:g}" height="{ty1 - ty0:g}" '
            f'fill="{colour}"/>',
            f'  <circle cx="{cx + dx:g}" cy="{cy:g}" r="{r:g}" fill="{colour}"/>',
        ])

    return '\n'.join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">',
        f'  <rect x="0.5" y="0.5" width="31" height="31" rx="1" fill="{TILE}" stroke="{EDGE}"/>',
        layer(-SLIP, CH_A),
        layer(SLIP, CH_B),
        layer(0, MINT),
        '</svg>',
        '',
    ])


def png(size: int) -> Image.Image:
    s = size * SUPERSAMPLE
    k = s / 32
    image = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    edge = max(k, SUPERSAMPLE)                  # at least one final pixel
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=1.0 * k, fill=EDGE)
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge),
                           radius=max(0, 1.0 * k - edge), fill=TILE)
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    w = max(LINE_W * k, 1.2 * SUPERSAMPLE)
    half = w / 2
    for dx, colour in layers:
        x0, y0, x1, y1 = BODY
        draw.rectangle(((x0 + dx) * k - half, y0 * k - half, (x1 + dx) * k + half, y1 * k + half),
                       outline=colour, width=round(w))
        tx0, ty0, tx1, ty1 = TOP
        draw.rectangle(((tx0 + dx) * k, ty0 * k, (tx1 + dx) * k, ty1 * k), fill=colour)
        cx, cy, r = LENS
        draw.ellipse(((cx + dx - r) * k, (cy - r) * k, (cx + dx + r) * k, (cy + r) * k),
                     fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-camera.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-camera-{size}.png'))
    print(f"wrote icons/spark-camera.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
