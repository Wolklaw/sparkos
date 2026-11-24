"""Draw the Spark Notes icon: a clipboard with three lines of text on a dark tile, with the
magenta and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-notes.svg and icons/spark-notes-<size>.png (16-512 px). Each PNG is drawn at
its own size from the same 32-unit grid as the SVG.

Run:  python files/spark-notes/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SLUG = 'spark-notes'
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#100f26', '#2c2a5c'
MINT, CH_A, CH_B = '#9be8b8', '#ff2e88', '#22d8ff'
BOARD = (7.0, 7.0, 25.0, 27.0)                   # the board, a rounded square outline
BOARD_W = 1.8
CLIP = (12.0, 4.5, 20.0, 9.5)                    # the clip, a filled bar over the top edge
LINES = ((11.0, 14.0, 21.0), (11.0, 18.0, 21.0), (11.0, 22.0, 17.0))   # x0, y, x1
LINE_W = 1.7
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        x0, y0, x1, y1 = BOARD
        cx0, cy0, cx1, cy1 = CLIP
        lines = '\n'.join(
            f'  <line x1="{a + dx:g}" y1="{y:g}" x2="{b + dx:g}" y2="{y:g}" stroke="{colour}" '
            f'stroke-width="{LINE_W:g}" stroke-linecap="square"/>' for a, y, b in LINES)
        return '\n'.join([
            f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" rx="1.5" '
            f'fill="none" stroke="{colour}" stroke-width="{BOARD_W:g}"/>',
            f'  <rect x="{cx0 + dx:g}" y="{cy0:g}" width="{cx1 - cx0:g}" height="{cy1 - cy0:g}" '
            f'rx="1" fill="{colour}"/>',
            lines,
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
    edge = max(k, SUPERSAMPLE)
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=1.0 * k, fill=EDGE)
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge),
                           radius=max(0, 1.0 * k - edge), fill=TILE)
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    for dx, colour in layers:
        w = max(BOARD_W * k, 1.2 * SUPERSAMPLE)
        lw = max(LINE_W * k, 1.0 * SUPERSAMPLE)
        x0, y0, x1, y1 = BOARD
        half = w / 2
        draw.rounded_rectangle(((x0 + dx) * k - half, y0 * k - half,
                                (x1 + dx) * k + half, y1 * k + half),
                               radius=1.5 * k, outline=colour, width=round(w))
        cx0, cy0, cx1, cy1 = CLIP
        draw.rounded_rectangle(((cx0 + dx) * k, cy0 * k, (cx1 + dx) * k, cy1 * k),
                               radius=1.0 * k, fill=colour)
        for a, y, b in LINES:
            draw.line((((a + dx) * k, y * k), ((b + dx) * k, y * k)), fill=colour, width=round(lw))
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
