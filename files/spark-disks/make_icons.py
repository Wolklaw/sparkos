"""Draw the Spark Disks icon: a drive (box, divider, light) on a dark tile, with the magenta
and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-disks.svg and icons/spark-disks-<size>.png (16-512 px). Each PNG is
drawn at its own size from the same 32-unit grid as the SVG (and as Mark in
sparkdisks/widgets.py).

Run:  python files/spark-disks/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
LINES = ((6, 9, 26, 9), (26, 9, 26, 23), (26, 23, 6, 23), (6, 23, 6, 9),
         (6, 17, 26, 17), (20, 20, 23, 20))
LINE_W = 1.8
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        return '\n'.join(
            f'  <line x1="{x0 + dx:g}" y1="{y0:g}" x2="{x1 + dx:g}" y2="{y1:g}" '
            f'stroke="{colour}" stroke-width="{LINE_W:g}" stroke-linecap="square"/>'
            for x0, y0, x1, y1 in LINES)

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
    edge = max(k, SUPERSAMPLE)
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=1.0 * k, fill=EDGE)
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge), radius=max(0, 1.0 * k - edge),
                           fill=TILE)
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    for dx, colour in layers:
        w = max(LINE_W * k, 1.2 * SUPERSAMPLE)
        for x0, y0, x1, y1 in LINES:
            draw.line([((x0 + dx) * k, y0 * k), ((x1 + dx) * k, y1 * k)], fill=colour,
                      width=round(w))
            r = w / 2
            for px_, py_ in (((x0 + dx) * k, y0 * k), ((x1 + dx) * k, y1 * k)):
                draw.rectangle((px_ - r, py_ - r, px_ + r, py_ + r), fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-disks.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-disks-{size}.png'))
    print(f"wrote icons/spark-disks.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
