"""Draw the Spark Run icon: a run prompt (a chevron and a cursor) in a frame on a dark tile,
with the magenta and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-run.svg and icons/spark-run-<size>.png (16-512 px). Each PNG is drawn at
its own size from the same 32-unit grid as the SVG (and as Mark in sparkrun/widgets.py).

Run:  python files/spark-run/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
FRAME = (6.5, 8.5, 25.5, 23.5)
CHEVRON = ((11, 12), (15, 16), (11, 20))
CURSOR = ((17, 20), (22, 20))
STROKE = 1.8
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        x0, y0, x1, y1 = FRAME
        chevron = ' '.join(f"{x + dx:g},{y:g}" for x, y in CHEVRON)
        (cx0, cy0), (cx1, cy1) = CURSOR
        return (f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
                f'fill="none" stroke="{colour}" stroke-width="{STROKE:g}"/>\n'
                f'  <polyline points="{chevron}" fill="none" stroke="{colour}" '
                f'stroke-width="{STROKE:g}" stroke-linecap="square" stroke-linejoin="miter"/>\n'
                f'  <line x1="{cx0 + dx:g}" y1="{cy0:g}" x2="{cx1 + dx:g}" y2="{cy1:g}" '
                f'stroke="{colour}" stroke-width="{STROKE:g}" stroke-linecap="square"/>')

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
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge), radius=max(0, 1.0 * k - edge),
                           fill=TILE)
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    for dx, colour in layers:
        w = max(STROKE * k, 1.2 * SUPERSAMPLE)
        half = w / 2
        x0, y0, x1, y1 = FRAME
        draw.rectangle(((x0 + dx) * k - half, y0 * k - half, (x1 + dx) * k + half, y1 * k + half),
                       outline=colour, width=round(w))
        draw.line([((x + dx) * k, y * k) for x, y in CHEVRON], fill=colour, width=round(w),
                  joint='curve')
        (cx0, cy), (cx1, _) = CURSOR
        draw.rectangle(((cx0 + dx) * k - half, cy * k - half, (cx1 + dx) * k + half, cy * k + half),
                       fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-run.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-run-{size}.png'))
    print(f"wrote icons/spark-run.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
