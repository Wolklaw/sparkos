"""Draw the Spark Snip icon: viewfinder brackets around lines of text on a dark tile, with the
magenta and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-snip.svg and icons/spark-snip-<size>.png (16-512 px). Each PNG is drawn at
its own size from the same 32-unit grid as the SVG, so strokes stay crisp at 16 px.

Run:  python files/spark-snip/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
CORNERS = ((6.5, 6.5, 1, 1), (25.5, 6.5, -1, 1), (6.5, 25.5, 1, -1), (25.5, 25.5, -1, -1))
ARM, BRACKET_W = 5.5, 1.8
ROWS = ((12.6, 10.0), (16.0, 10.0), (19.4, 6.0))
ROWS_SMALL = ((13.4, 10.0), (18.6, 6.0))           # two lines read better at 16-22 px
TEXT_X, TEXT_W = 11.0, 1.7
SLIP = 1.0


def shapes(small: bool):
    """Every stroke as (points, width), in 32-unit coordinates."""
    out = []
    for cx, cy, dx, dy in CORNERS:
        out.append((((cx, cy + dy * ARM), (cx, cy), (cx + dx * ARM, cy)), BRACKET_W))
    for y, length in (ROWS_SMALL if small else ROWS):
        out.append((((TEXT_X, y), (TEXT_X + length, y)), TEXT_W))
    return out


def svg() -> str:
    def layer(dx, colour):
        lines = []
        for points, width in shapes(small=False):
            d = ' '.join(f"{x + dx:g},{y:g}" for x, y in points)
            lines.append(f'    <polyline points="{d}" stroke-width="{width:g}"/>')
        return (f'  <g fill="none" stroke="{colour}" stroke-linecap="square" '
                f'stroke-linejoin="miter">\n' + '\n'.join(lines) + '\n  </g>')

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
    small = size <= 22
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    for dx, colour in layers:
        for points, width in shapes(small):
            w = max(width * k, 1.2 * SUPERSAMPLE)
            pts = [((x + dx) * k, y * k) for x, y in points]
            draw.line(pts, fill=colour, width=round(w), joint=None)
            half = w / 2
            for x, y in (pts[0], pts[-1]):     # square caps
                draw.rectangle((x - half, y - half, x + half, y + half), fill=colour)
            if len(pts) == 3:                  # sharp outer corner
                x, y = pts[1]
                draw.rectangle((x - half, y - half, x + half, y + half), fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-snip.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-snip-{size}.png'))
    print(f"wrote icons/spark-snip.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
