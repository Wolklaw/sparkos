"""Draw the Spark Archive icon: a box with a zip down its middle on a dark tile, with the
magenta and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-archive.svg and icons/spark-archive-<size>.png (16-512 px). Each PNG is drawn
at its own size from the same 32-unit grid as the SVG (and as Mark in sparkarchive/widgets.py).

Run:  python files/spark-archive/make_icons.py
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
FRAME_W = 1.8
TEETH = ((14, 10.5, 16, 10.5), (16, 12.5, 18, 12.5), (14, 14.5, 16, 14.5), (16, 16.5, 18, 16.5))
TEETH_W = 1.3
TAB = (14.5, 18, 17.5, 22)
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        x0, y0, x1, y1 = FRAME
        parts = [f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
                 f'fill="none" stroke="{colour}" stroke-width="{FRAME_W:g}"/>']
        for a, b, c, d in TEETH:
            parts.append(f'  <line x1="{a + dx:g}" y1="{b:g}" x2="{c + dx:g}" y2="{d:g}" '
                         f'stroke="{colour}" stroke-width="{TEETH_W:g}"/>')
        tx0, ty0, tx1, ty1 = TAB
        parts.append(f'  <rect x="{tx0 + dx:g}" y="{ty0:g}" width="{tx1 - tx0:g}" '
                     f'height="{ty1 - ty0:g}" fill="{colour}"/>')
        return '\n'.join(parts)

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
        w = max(FRAME_W * k, 1.2 * SUPERSAMPLE)
        x0, y0, x1, y1 = FRAME
        half = w / 2
        draw.rectangle(((x0 + dx) * k - half, y0 * k - half, (x1 + dx) * k + half, y1 * k + half),
                       outline=colour, width=round(w))
        tw = round(max(TEETH_W * k, 1.0 * SUPERSAMPLE))
        for a, b, c, d in TEETH:
            draw.line(((a + dx) * k, b * k, (c + dx) * k, d * k), fill=colour, width=tw)
        tx0, ty0, tx1, ty1 = TAB
        draw.rectangle(((tx0 + dx) * k, ty0 * k, (tx1 + dx) * k, ty1 * k), fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-archive.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-archive-{size}.png'))
    print(f"wrote icons/spark-archive.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
