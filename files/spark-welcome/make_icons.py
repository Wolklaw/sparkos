"""Draw Spark Welcome's icons and the SparkOS bot for the welcome page.

- icons/spark-welcome.svg and icons/spark-welcome-<size>.png (16-512 px): an arrow going in
  through an open frame on a dark tile, with the magenta and cyan channels slipping out of
  register behind the mint mark. Same 32-unit grid as Mark in sparkwelcome/widgets.py.
- icons/sparkos-bot-<size>.png (160, 240, 320 px): branding/sparkos-bot.svg rendered with
  Pillow. Only the shapes that file uses are supported (rect, line, path with M/H/V/L/Z, use
  with the two tint filters), so no SVG library is needed.

Run:  python files/spark-welcome/make_icons.py
"""

import math
import os
import re
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'icons')
BOT_SVG = os.path.join(HERE, '..', '..', 'branding', 'sparkos-bot.svg')
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
BOT_SIZES = (160, 240, 320)
SUPERSAMPLE = 8

TILE, EDGE = '#0b1a1c', '#1f6a66'
MINT, CH_A, CH_B = '#3de8c8', '#ff2e88', '#22d8ff'
FRAME = ((16.5, 11), (16.5, 7.5), (25.5, 7.5), (25.5, 24.5), (16.5, 24.5), (16.5, 21))
FRAME_W = 1.8
SHAFT = (5, 14.8, 15, 17.2)
HEAD = ((14, 11.5), (14, 20.5), (21, 16))
SLIP = 1.0


# ─── App icon ─────────────────────────────────────────────────

def svg() -> str:
    def layer(dx, colour):
        pts = ' '.join(f"{x + dx:g},{y:g}" for x, y in FRAME)
        head = ' '.join(f"{x + dx:g},{y:g}" for x, y in HEAD)
        x0, y0, x1, y1 = SHAFT
        return (f'  <polyline points="{pts}" fill="none" stroke="{colour}" '
                f'stroke-width="{FRAME_W:g}" stroke-linecap="square"/>\n'
                f'  <rect x="{x0 + dx:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
                f'fill="{colour}"/>\n'
                f'  <polygon points="{head}" fill="{colour}"/>')

    return '\n'.join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">',
        f'  <rect x="0.5" y="0.5" width="31" height="31" rx="1" fill="{TILE}" stroke="{EDGE}"/>',
        layer(-SLIP, CH_A),
        layer(SLIP, CH_B),
        layer(0, MINT),
        '</svg>',
        '',
    ])


def thick_line(draw, p0, p1, width, colour, cap='butt'):
    """A line as a polygon, so its width is exact at every angle."""
    (x0, y0), (x1, y1) = p0, p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length == 0:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    if cap == 'square':
        x0, y0, x1, y1 = x0 - ux * width / 2, y0 - uy * width / 2, x1 + ux * width / 2, \
            y1 + uy * width / 2
    nx, ny = -uy * width / 2, ux * width / 2
    draw.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny),
                  (x0 - nx, y0 - ny)], fill=colour)


def polyline(draw, points, width, colour, cap='butt'):
    for i, (a, b) in enumerate(zip(points, points[1:])):
        thick_line(draw, a, b, width, colour, cap)
    for x, y in points[1:-1]:                     # mitred corners, near enough at icon sizes
        draw.rectangle((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=colour)


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
        polyline(draw, [((x + dx) * k, y * k) for x, y in FRAME], w, colour, 'square')
        x0, y0, x1, y1 = SHAFT
        draw.rectangle(((x0 + dx) * k, y0 * k, (x1 + dx) * k, y1 * k), fill=colour)
        draw.polygon([((x + dx) * k, y * k) for x, y in HEAD], fill=colour)
    return image.resize((size, size), Image.Resampling.LANCZOS)


# ─── The SparkOS bot ──────────────────────────────────────────

NS = '{http://www.w3.org/2000/svg}'
INHERITED = ('fill', 'stroke', 'stroke-width', 'stroke-linecap')


def _path_points(d: str):
    """M/H/V/L/Z absolute paths, as (points, closed)."""
    tokens = re.findall(r'[MHVLZmhvlz]|-?\d*\.?\d+', d)
    points, closed, cmd, i = [], False, None, 0
    x = y = 0.0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok.upper()
            i += 1
            if cmd == 'Z':
                closed = True
            continue
        if cmd in ('M', 'L'):
            x, y = float(tokens[i]), float(tokens[i + 1])
            i += 2
        elif cmd == 'H':
            x = float(tok)
            i += 1
        elif cmd == 'V':
            y = float(tok)
            i += 1
        else:
            raise ValueError(f"unsupported path command in {d!r}")
        points.append((x, y))
    return points, closed


def _draw_element(draw, el, style, k, dx):
    tag = el.tag.replace(NS, '')
    style = dict(style)
    for key in INHERITED:
        if el.get(key) is not None:
            style[key] = el.get(key)
    if tag == 'g':
        for child in el:
            _draw_element(draw, child, style, k, dx)
        return
    fill = style.get('fill', '#000000')
    stroke = style.get('stroke', 'none')
    sw = float(style.get('stroke-width', '1')) * k
    cap = style.get('stroke-linecap', 'butt')

    def P(x, y):
        return ((float(x) + dx) * k, float(y) * k)

    if tag == 'rect':
        x, y = float(el.get('x', 0)), float(el.get('y', 0))
        w, h = float(el.get('width')), float(el.get('height'))
        r = float(el.get('rx', 0)) * k
        x0, y0 = P(x, y)
        x1, y1 = P(x + w, y + h)
        if stroke != 'none':
            half = sw / 2
            draw.rounded_rectangle((x0 - half, y0 - half, x1 + half, y1 + half), radius=r + half,
                                   fill=stroke)
            if fill != 'none':
                draw.rounded_rectangle((x0 + half, y0 + half, x1 - half, y1 - half),
                                       radius=max(0, r - half), fill=fill)
        elif fill != 'none':
            draw.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=fill)
    elif tag == 'line':
        thick_line(draw, P(el.get('x1'), el.get('y1')), P(el.get('x2'), el.get('y2')), sw,
                   stroke, cap)
    elif tag == 'path':
        points, closed = _path_points(el.get('d'))
        pts = [P(x, y) for x, y in points]
        if closed and fill != 'none':
            draw.polygon(pts, fill=fill)
        if stroke != 'none':
            polyline(draw, pts + ([pts[0]] if closed else []), sw, stroke, cap)


def _layer(root, element, size, dx=0.0):
    s = size * SUPERSAMPLE
    k = s / float(root.get('viewBox').split()[2])
    image = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    _draw_element(ImageDraw.Draw(image), element, {}, k, dx)
    return image


def _tint(image, colour, opacity):
    alpha = image.getchannel('A').point(lambda a: int(a * opacity))
    solid = Image.new('RGBA', image.size, colour)
    solid.putalpha(alpha)
    return solid


def bot(size: int, path: str = BOT_SVG) -> Image.Image:
    root = ET.parse(path).getroot()
    defs = {el.get('id'): el for el in root.iter() if el.get('id')}
    canvas = Image.new('RGBA', (size * SUPERSAMPLE,) * 2, (0, 0, 0, 0))
    tints = {'url(#tint-magenta)': CH_A, 'url(#tint-cyan)': CH_B}
    for el in root:
        tag = el.tag.replace(NS, '')
        if tag == 'use':
            ref = (el.get('href') or el.get('{http://www.w3.org/1999/xlink}href') or '')[1:]
            match = re.search(r'translate\(\s*(-?[\d.]+)', el.get('transform', ''))
            layer = _layer(root, defs[ref], size, float(match.group(1)) if match else 0.0)
            if el.get('filter') in tints:
                layer = _tint(layer, tints[el.get('filter')], float(el.get('opacity', '1')))
            canvas.alpha_composite(layer)
        elif tag in ('g', 'rect', 'line', 'path'):
            canvas.alpha_composite(_layer(root, el, size))
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'spark-welcome.svg'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg())
    for size in SIZES:
        png(size).save(os.path.join(OUT, f'spark-welcome-{size}.png'), optimize=True)
    for size in BOT_SIZES:
        bot(size).save(os.path.join(OUT, f'sparkos-bot-{size}.png'), optimize=True)
    print(f"wrote icons/spark-welcome.svg, {len(SIZES)} icon PNGs and "
          f"{len(BOT_SIZES)} bot PNGs ({', '.join(map(str, BOT_SIZES))} px)")


if __name__ == '__main__':
    main()
