"""Draw the Spark Settings icon: three sliders on a dark tile, with the magenta and cyan
channels slipping out of register behind the mint mark.

Writes icons/spark-settings.svg and icons/spark-settings-<size>.png (16-512 px).

Run:  python files/spark-settings/make_icons.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
ROWS = ((10, 21), (16, 11), (22, 17))       # y, knob x on a 32-unit grid
LEFT, RIGHT, KNOB, LINE_W = 6, 26, 2.6, 1.8
SLIP = 1.0


def svg() -> str:
    def layer(dx, colour):
        parts = []
        for y, kx in ROWS:
            parts.append(f'  <line x1="{LEFT + dx:g}" y1="{y}" x2="{RIGHT + dx:g}" y2="{y}" '
                         f'stroke="{colour}" stroke-width="{LINE_W:g}"/>')
            parts.append(f'  <rect x="{kx - KNOB + dx:g}" y="{y - KNOB:g}" width="{2 * KNOB:g}" '
                         f'height="{2 * KNOB:g}" fill="{TILE}" stroke="{colour}" stroke-width="1.4"/>')
        return '\n'.join(parts)

    return '\n'.join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">',
        f'  <rect x="0.5" y="0.5" width="31" height="31" rx="1" fill="{TILE}" stroke="{EDGE}"/>',
        layer(-SLIP, CH_A), layer(SLIP, CH_B), layer(0, MINT), '</svg>', ''])


def png(size: int) -> Image.Image:
    s = size * SUPERSAMPLE
    k = s / 32
    image = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    edge = max(k, SUPERSAMPLE)
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=1.0 * k, fill=EDGE)
    draw.rounded_rectangle((edge, edge, s - 1 - edge, s - 1 - edge),
                           radius=max(0, 1.0 * k - edge), fill=TILE)
    layers = ((-SLIP, CH_A), (SLIP, CH_B), (0, MINT)) if size >= 24 else ((0, MINT),)
    lw = max(LINE_W * k, 1.2 * SUPERSAMPLE)
    for dx, colour in layers:
        for y, kx in ROWS:
            draw.rectangle(((LEFT + dx) * k, y * k - lw / 2, (RIGHT + dx) * k, y * k + lw / 2), fill=colour)
            draw.rectangle(((kx - KNOB + dx) * k, (y - KNOB) * k, (kx + KNOB + dx) * k, (y + KNOB) * k),
                           fill=TILE, outline=colour, width=round(max(1.4 * k, SUPERSAMPLE)))
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-settings.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-settings-{size}.png'))
    print(f"wrote icons/spark-settings.svg and {len(SIZES)} PNGs")


if __name__ == '__main__':
    main()
