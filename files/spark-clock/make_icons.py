"""Draw the Spark Clock icon: a clock face with two hands on a dark tile, with the magenta and
cyan channels slipping out of register behind the mint mark.

Writes icons/spark-clock.svg and icons/spark-clock-<size>.png (16-512 px). Each PNG is drawn at
its own size from the same 32-unit grid as the SVG (and as Mark in sparkclock/widgets.py).

Run:  python files/spark-clock/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
CENTRE, RADIUS = (16.0, 16.5), 9.5
HANDS = ((16.0, 16.5, 16.0, 10.0), (16.0, 16.5, 21.0, 19.5))
LINE_W = 1.6
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        cx, cy = CENTRE
        out = [f'  <circle cx="{cx + dx:g}" cy="{cy:g}" r="{RADIUS:g}" fill="none" '
               f'stroke="{colour}" stroke-width="{LINE_W:g}"/>']
        for x0, y0, x1, y1 in HANDS:
            out.append(f'  <line x1="{x0 + dx:g}" y1="{y0:g}" x2="{x1 + dx:g}" y2="{y1:g}" '
                       f'stroke="{colour}" stroke-width="{LINE_W:g}" stroke-linecap="square"/>')
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
    w = max(LINE_W * k, 1.2 * SUPERSAMPLE)
    cx, cy = CENTRE
    for dx, colour in layers:
        box = ((cx + dx - RADIUS) * k, (cy - RADIUS) * k, (cx + dx + RADIUS) * k,
               (cy + RADIUS) * k)
        draw.ellipse(box, outline=colour, width=round(w))
        for x0, y0, x1, y1 in HANDS:
            draw.line(((x0 + dx) * k, y0 * k, (x1 + dx) * k, y1 * k), fill=colour,
                      width=round(w))
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-clock.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-clock-{size}.png'))
    print(f"wrote icons/spark-clock.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
