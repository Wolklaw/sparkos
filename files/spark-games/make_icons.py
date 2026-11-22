"""Draw the Spark Games icon: a gamepad (body, d-pad, two buttons) on a dark tile, with the
magenta and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-games.svg and icons/spark-games-<size>.png (16-512 px). Each PNG is drawn at
its own size from the same 32-unit grid as the SVG (and as Mark in sparkgames/widgets.py).

Run:  python files/spark-games/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
BODY = (5.5, 10.5, 26.5, 22.5)
BODY_W = 1.8
FILLED = (                       # d-pad (two bars) and the two buttons
    (8.5, 15.2, 14.5, 17.8), (10.2, 13.5, 12.8, 19.5),
    (18.6, 13.4, 21.2, 16.0), (21.8, 17.0, 24.4, 19.6),
)
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        x0, y0, x1, y1 = BODY
        parts = [f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
                 f'fill="none" stroke="{colour}" stroke-width="{BODY_W:g}"/>']
        for a, b, c, d in FILLED:
            parts.append(f'  <rect x="{a + dx:g}" y="{b:g}" width="{c - a:g}" height="{d - b:g}" '
                         f'fill="{colour}"/>')
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
        w = max(BODY_W * k, 1.2 * SUPERSAMPLE)
        x0, y0, x1, y1 = BODY
        half = w / 2
        draw.rectangle(((x0 + dx) * k - half, y0 * k - half, (x1 + dx) * k + half, y1 * k + half),
                       outline=colour, width=round(w))
        for a, b, c, d in FILLED:
            draw.rectangle(((a + dx) * k, b * k, (c + dx) * k, d * k), fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-games.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-games-{size}.png'))
    print(f"wrote icons/spark-games.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
