"""Draw the Spark Terminal icon: a prompt chevron and a cursor bar in a window frame on a dark
tile, with the magenta and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-terminal.svg and icons/spark-terminal-<size>.png (16-512 px). Each PNG is
drawn at its own size from the same 32-unit grid as the SVG.

Run:  python files/spark-terminal/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SLUG = 'spark-terminal'
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

# the SparkOS colours (core.CHROME)
TILE, EDGE = '#100f26', '#2c2a5c'
MINT, CH_A, CH_B = '#9be8b8', '#ff2e88', '#22d8ff'
FRAME = (5.5, 7.5, 26.5, 24.5)
FRAME_W = 1.8
BAR_Y = 11.0                                     # the window's title bar line
CHEVRON = ((10.0, 14.0), (14.0, 17.5), (10.0, 21.0))
CURSOR = (16.0, 20.2, 22.0)                       # x0, y, x1
LINE_W = 1.7
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        x0, y0, x1, y1 = FRAME
        points = ' '.join(f'{x + dx:g},{y:g}' for x, y in CHEVRON)
        cx0, cy, cx1 = CURSOR
        return '\n'.join([
            f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
            f'fill="none" stroke="{colour}" stroke-width="{FRAME_W:g}"/>',
            f'  <line x1="{x0 + dx:g}" y1="{BAR_Y:g}" x2="{x1 + dx:g}" y2="{BAR_Y:g}" '
            f'stroke="{colour}" stroke-width="{LINE_W * 0.7:g}"/>',
            f'  <polyline points="{points}" fill="none" stroke="{colour}" '
            f'stroke-width="{LINE_W:g}" stroke-linecap="square" stroke-linejoin="miter"/>',
            f'  <line x1="{cx0 + dx:g}" y1="{cy:g}" x2="{cx1 + dx:g}" y2="{cy:g}" '
            f'stroke="{colour}" stroke-width="{LINE_W:g}"/>',
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
    edge = max(k, SUPERSAMPLE)                   # at least one final pixel
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=1.0 * k, fill=EDGE)
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge),
                           radius=max(0, 1.0 * k - edge), fill=TILE)
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    for dx, colour in layers:
        w = max(FRAME_W * k, 1.2 * SUPERSAMPLE)
        lw = max(LINE_W * k, 1.0 * SUPERSAMPLE)
        x0, y0, x1, y1 = FRAME
        half = w / 2
        draw.rectangle(((x0 + dx) * k - half, y0 * k - half, (x1 + dx) * k + half, y1 * k + half),
                       outline=colour, width=round(w))
        bar = max(lw * 0.7, SUPERSAMPLE)
        draw.rectangle(((x0 + dx) * k, BAR_Y * k - bar / 2, (x1 + dx) * k, BAR_Y * k + bar / 2),
                       fill=colour)
        points = [((x + dx) * k, y * k) for x, y in CHEVRON]
        draw.line(points, fill=colour, width=round(lw), joint='curve')
        cx0, cy, cx1 = CURSOR
        draw.rectangle(((cx0 + dx) * k, cy * k - lw / 2, (cx1 + dx) * k, cy * k + lw / 2),
                       fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f'{SLUG}.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'{SLUG}-{size}.png'))
    print(f"wrote icons/{SLUG}.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
