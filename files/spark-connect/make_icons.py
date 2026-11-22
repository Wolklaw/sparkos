"""Draw the Spark Connect icon: two machines joined by a line on a dark tile, with the magenta
and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-connect.svg and icons/spark-connect-<size>.png (16-512 px). Each PNG is drawn
at its own size from the same 32-unit grid as the SVG (and as Mark in sparkconnect/widgets.py).

Run:  python files/spark-connect/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
NODES = ((5.5, 8.5, 12.5, 15.5), (19.5, 16.5, 26.5, 23.5))
LINK = ((12.5, 12), (16, 12), (16, 20), (19.5, 20))
STROKE = 1.8
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        out = []
        for x0, y0, x1, y1 in NODES:
            out.append(f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" '
                       f'height="{y1 - y0:g}" fill="none" stroke="{colour}" '
                       f'stroke-width="{STROKE:g}"/>')
        pts = ' '.join(f"{x + dx:g},{y:g}" for x, y in LINK)
        out.append(f'  <polyline points="{pts}" fill="none" stroke="{colour}" '
                   f'stroke-width="{STROKE:g}" stroke-linejoin="miter"/>')
        return '\n'.join(out)

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
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge),
                           radius=max(0, 1.0 * k - edge), fill=TILE)
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    for dx, colour in layers:
        w = max(STROKE * k, 1.2 * SUPERSAMPLE)
        half = w / 2
        for x0, y0, x1, y1 in NODES:
            draw.rectangle(((x0 + dx) * k - half, y0 * k - half, (x1 + dx) * k + half,
                            y1 * k + half), outline=colour, width=round(w))
        draw.line([((x + dx) * k, y * k) for x, y in LINK], fill=colour, width=round(w),
                  joint='curve')
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-connect.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-connect-{size}.png'))
    print(f"wrote icons/spark-connect.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
