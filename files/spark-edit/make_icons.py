"""Draw the Spark Edit icon: three lines of text and a caret in a frame on a dark tile, with
the magenta and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-edit.svg and icons/spark-edit-<size>.png (16-512 px). Each PNG is drawn at
its own size from the same 32-unit grid as the SVG (and as Mark in sparkedit/widgets.py).

Run:  python files/spark-edit/make_icons.py
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
LINES = ((9.5, 12.5, 22.5), (9.5, 16, 19.5), (9.5, 19.5, 14.5))     # x0, y, x1
LINE_W = 1.4
CARET = (16.8, 17.2, 16.8, 21.8)
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        x0, y0, x1, y1 = FRAME
        parts = [f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
                 f'fill="none" stroke="{colour}" stroke-width="{FRAME_W:g}"/>']
        for lx0, y, lx1 in LINES:
            parts.append(f'  <line x1="{lx0 + dx:g}" y1="{y:g}" x2="{lx1 + dx:g}" y2="{y:g}" '
                         f'stroke="{colour}" stroke-width="{LINE_W:g}"/>')
        cx0, cy0, cx1, cy1 = CARET
        parts.append(f'  <line x1="{cx0 + dx:g}" y1="{cy0:g}" x2="{cx1 + dx:g}" y2="{cy1:g}" '
                     f'stroke="{colour}" stroke-width="{LINE_W:g}"/>')
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
        lw = max(LINE_W * k, 1.0 * SUPERSAMPLE)
        x0, y0, x1, y1 = FRAME
        half = w / 2
        draw.rectangle(((x0 + dx) * k - half, y0 * k - half, (x1 + dx) * k + half, y1 * k + half),
                       outline=colour, width=round(w))
        for lx0, y, lx1 in LINES:
            draw.rectangle(((lx0 + dx) * k, y * k - lw / 2, (lx1 + dx) * k, y * k + lw / 2),
                           fill=colour)
        cx0, cy0, _cx1, cy1 = CARET
        draw.rectangle(((cx0 + dx) * k - lw / 2, cy0 * k, (cx0 + dx) * k + lw / 2, cy1 * k),
                       fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-edit.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-edit-{size}.png'))
    print(f"wrote icons/spark-edit.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
