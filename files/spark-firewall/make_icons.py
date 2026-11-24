"""Draw the Spark Firewall icon: a shield with a seam on a dark tile, with the magenta
and cyan channels slipping out of register behind the mint mark.

Writes icons/spark-firewall.svg and icons/spark-firewall-<size>.png (16-512 px). Each PNG is
drawn at its own size from the same 32-unit grid as the SVG (and as Mark in
sparkfirewall/widgets.py).

Run:  python files/spark-firewall/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
SHIELD = ((16, 6), (25, 9.5), (25, 16.5), (16, 26), (7, 16.5), (7, 9.5))
SEAM = (16, 10.5, 16, 21)
LINE_W = 1.8
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        pts = ' '.join(f'{x + dx:g},{y:g}' for x, y in SHIELD)
        x0, y0, x1, y1 = SEAM
        return (f'  <polygon points="{pts}" fill="none" stroke="{colour}" stroke-width="{LINE_W:g}" '
                f'stroke-linejoin="round"/>\n'
                f'  <line x1="{x0 + dx:g}" y1="{y0:g}" x2="{x1 + dx:g}" y2="{y1:g}" '
                f'stroke="{colour}" stroke-width="{LINE_W:g}"/>')

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
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge), radius=max(0, 1.0 * k - edge),
                           fill=TILE)
    # below 24 px the ghosts smear into the mark, so the small sizes stay clean
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    for dx, colour in layers:
        w = round(max(LINE_W * k, 1.2 * SUPERSAMPLE))
        pts = [((x + dx) * k, y * k) for x, y in SHIELD]
        draw.line(pts + [pts[0]], fill=colour, width=w, joint='curve')
        x0, y0, x1, y1 = SEAM
        draw.line([((x0 + dx) * k, y0 * k), ((x1 + dx) * k, y1 * k)], fill=colour, width=w)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-firewall.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-firewall-{size}.png'))
    print(f"wrote icons/spark-firewall.svg and {len(SIZES)} PNGs ({', '.join(map(str, SIZES))} px)")


if __name__ == '__main__':
    main()
