"""Draw the Spark Files icon: a folder with two sheets in it on a dark tile, with the magenta
and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-files.svg and icons/spark-files-<size>.png (16-512 px). Each PNG is drawn
at its own size from the same 32-unit grid as the SVG (and as Mark in sparkfiles/widgets.py).

Run:  python files/spark-files/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
FOLDER = (6, 10, 13, 10, 15, 12.5, 26, 12.5, 26, 24, 6, 24)
FOLDER_W = 1.8
SHEETS = ((10, 16.5, 22), (10, 20, 18.5))     # x0, y, x1
SHEET_W = 1.4
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        pts = ' '.join(f'{FOLDER[i] + dx:g},{FOLDER[i + 1]:g}' for i in range(0, len(FOLDER), 2))
        parts = [f'  <polygon points="{pts}" fill="none" stroke="{colour}" '
                 f'stroke-width="{FOLDER_W:g}" stroke-linejoin="miter"/>']
        for x0, y, x1 in SHEETS:
            parts.append(f'  <line x1="{x0 + dx:g}" y1="{y:g}" x2="{x1 + dx:g}" y2="{y:g}" '
                         f'stroke="{colour}" stroke-width="{SHEET_W:g}"/>')
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
    edge = max(k, SUPERSAMPLE)
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=1.0 * k, fill=EDGE)
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge),
                           radius=max(0, 1.0 * k - edge), fill=TILE)
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    for dx, colour in layers:
        w = round(max(FOLDER_W * k, 1.2 * SUPERSAMPLE))
        lw = max(SHEET_W * k, 1.0 * SUPERSAMPLE)
        pts = [((FOLDER[i] + dx) * k, FOLDER[i + 1] * k) for i in range(0, len(FOLDER), 2)]
        draw.line(pts + [pts[0]], fill=colour, width=w, joint='curve')
        for x0, y, x1 in SHEETS:
            draw.rectangle(((x0 + dx) * k, y * k - lw / 2, (x1 + dx) * k, y * k + lw / 2),
                           fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-files.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-files-{size}.png'))
    print(f"wrote icons/spark-files.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
