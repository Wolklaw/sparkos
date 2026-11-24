"""Draw the Spark Emoji icon: a face made of two square eyes and a smile on a dark tile, with
the magenta and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-emoji.svg and icons/spark-emoji-<size>.png (16-512 px). Each PNG is drawn
at its own size from the same 32-unit grid as the SVG.

Run:  python files/spark-emoji/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SLUG = 'spark-emoji'
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#100f26', '#2c2a5c'
MINT, CH_A, CH_B = '#9be8b8', '#ff2e88', '#22d8ff'
FACE = (6.0, 6.0, 26.0, 26.0)                    # the face outline, a rounded square
FACE_W = 1.8
EYES = ((11.0, 12.0, 13.6, 15.2), (18.4, 12.0, 21.0, 15.2))
SMILE = ((10.5, 19.0), (12.5, 21.6), (19.5, 21.6), (21.5, 19.0))
LINE_W = 1.7
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        x0, y0, x1, y1 = FACE
        points = ' '.join(f'{x + dx:g},{y:g}' for x, y in SMILE)
        eyes = '\n'.join(
            f'  <rect x="{ex0 + dx:g}" y="{ey0:g}" width="{ex1 - ex0:g}" height="{ey1 - ey0:g}" '
            f'fill="{colour}"/>' for ex0, ey0, ex1, ey1 in EYES)
        return '\n'.join([
            f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" rx="1.5" '
            f'fill="none" stroke="{colour}" stroke-width="{FACE_W:g}"/>',
            eyes,
            f'  <polyline points="{points}" fill="none" stroke="{colour}" '
            f'stroke-width="{LINE_W:g}" stroke-linecap="square" stroke-linejoin="miter"/>',
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
        w = max(FACE_W * k, 1.2 * SUPERSAMPLE)
        lw = max(LINE_W * k, 1.0 * SUPERSAMPLE)
        x0, y0, x1, y1 = FACE
        half = w / 2
        draw.rounded_rectangle(((x0 + dx) * k - half, y0 * k - half,
                                (x1 + dx) * k + half, y1 * k + half),
                               radius=1.5 * k, outline=colour, width=round(w))
        for ex0, ey0, ex1, ey1 in EYES:
            draw.rectangle(((ex0 + dx) * k, ey0 * k, (ex1 + dx) * k, ey1 * k), fill=colour)
        points = [((x + dx) * k, y * k) for x, y in SMILE]
        draw.line(points, fill=colour, width=round(lw), joint='curve')
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
