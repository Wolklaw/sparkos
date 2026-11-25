"""Annotating a screenshot: the model and the renderer. No Tk in here, so it is tested on plain
generated images.

Every coordinate and size is in pixels of the full-resolution image, never of the screen. The
editor window scales the picture to fit and converts mouse positions back before it makes an
Item, so a 4K capture, a 1.5x desktop and a 1x desktop all come out the same.

An Item is frozen: undo and redo only swap tuples, so each step is cheap whatever the image size.
"""

import math
import os
from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

Point = Tuple[float, float]
Box = Tuple[int, int, int, int]

TOOLS = ("arrow", "rect", "ellipse", "pen", "highlight", "text", "step", "pixelate")
SHAPE_TOOLS = ("arrow", "rect", "ellipse", "pixelate")     # drawn by dragging two corners
STROKE_TOOLS = ("pen", "highlight")                         # drawn by dragging a path
PRESET_COLOURS = ("#ff2e88", "#22d8ff", "#f4c95d", "#3de8c8", "#ffffff", "#000000")
SUPERSAMPLE = 3                 # shapes are drawn 3x larger, then shrunk, for smooth edges
HIGHLIGHT_ALPHA = 0.4
MAX_TEXT_CHARS = 2000

FONT_PATHS = (
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/google-noto-vf/NotoSans[wdth,wght].ttf",
)


@dataclass(frozen=True)
class Item:
    kind: str                           # one of TOOLS
    points: Tuple[Point, ...]           # two corners for shapes, a path for strokes, one point
    colour: str = "#ff2e88"             # for text and steps
    width: float = 4.0                  # stroke width in image pixels (text size, step size, ...)
    text: str = ""                      # for text; for a step, its number


def default_width(size: Tuple[int, int]) -> int:
    """A stroke that reads on a 1080p shot and on a 4K one."""
    return max(3, round(max(size) / 320))


def hex_to_rgb(colour: str) -> Tuple[int, int, int]:
    colour = colour.lstrip("#")
    if len(colour) == 3:
        colour = "".join(c * 2 for c in colour)
    return int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16)


def text_size(item: Item) -> int:
    return max(12, int(round(item.width * 4)))


def step_radius(item: Item) -> float:
    return max(10.0, item.width * 3.2)


_font_cache = {}


def load_font(size: int) -> ImageFont.ImageFont:
    if size in _font_cache:
        return _font_cache[size]
    font = None
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
    if font is None:
        try:
            font = ImageFont.load_default(size)
        except TypeError:                      # Pillow older than 10.1: one fixed size
            font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def contrast_colour(colour: str) -> str:
    r, g, b = hex_to_rgb(colour)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"


def normalise(a: Point, b: Point) -> Box:
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return int(math.floor(x0)), int(math.floor(y0)), int(math.ceil(x1)), int(math.ceil(y1))


def clamp_box(box: Box, size: Tuple[int, int]) -> Optional[Box]:
    """The part of box inside the image, or None when nothing of it is left."""
    x0, y0 = max(0, box[0]), max(0, box[1])
    x1, y1 = min(size[0], box[2]), min(size[1], box[3])
    return (x0, y0, x1, y1) if x1 - x0 >= 1 and y1 - y0 >= 1 else None


# drawing ----------------------------------------------------------------------------------

def _bounds(item: Item, size: Tuple[int, int]) -> Box:
    """A box (padded, may leave the image) that holds everything the item draws."""
    xs = [p[0] for p in item.points]
    ys = [p[1] for p in item.points]
    pad = item.width * 3 + 4
    if item.kind == "text":
        font = load_font(text_size(item))
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        box = probe.multiline_textbbox((0, 0), item.text or " ", font=font)
        return (int(xs[0]) - 4, int(ys[0]) - 4, int(xs[0] + box[2]) + 8, int(ys[0] + box[3]) + 8)
    if item.kind == "step":
        r = step_radius(item) + 3
        return int(xs[0] - r), int(ys[0] - r), int(xs[0] + r) + 1, int(ys[0] + r) + 1
    return (int(min(xs) - pad), int(min(ys) - pad), int(max(xs) + pad) + 1, int(max(ys) + pad) + 1)


def _draw_shape(d: ImageDraw.ImageDraw, item: Item, k: float, ox: float, oy: float, fill) -> None:
    """Draw item on d, with every coordinate moved by (-ox, -oy) then scaled by k."""
    pts = [((x - ox) * k, (y - oy) * k) for x, y in item.points]
    w = max(1, int(round(item.width * k)))
    if item.kind == "rect":
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        d.rectangle((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), outline=fill, width=w)
    elif item.kind == "ellipse":
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        if abs(x1 - x0) >= 1 and abs(y1 - y0) >= 1:
            d.ellipse((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), outline=fill, width=w)
    elif item.kind == "arrow":
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1:
            return
        head = min(length * 0.6, max(w * 3.5, 14 * k))
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        bx, by = x1 - ux * head * 0.8, y1 - uy * head * 0.8          # where the shaft meets the head
        d.line((x0, y0, bx, by), fill=fill, width=w)
        half = head * 0.5
        d.polygon([(x1, y1), (bx - uy * half, by + ux * half), (bx + uy * half, by - ux * half)],
                  fill=fill)
    elif item.kind in STROKE_TOOLS:
        if len(pts) == 1:
            r = w / 2
            d.ellipse((pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r), fill=fill)
            return
        d.line(pts, fill=fill, width=w, joint="curve")
        r = w / 2 - 0.5                                        # round caps
        for x, y in (pts[0], pts[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=fill)
    elif item.kind == "step":
        x, y = pts[0]
        r = step_radius(item) * k
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _stamp(canvas: Image.Image, item: Item) -> None:
    """Draw one vector item (not text, not pixelate) onto canvas, anti-aliased."""
    left, top, right, bottom = _bounds(item, canvas.size)
    box = clamp_box((left, top, right, bottom), canvas.size)
    if box is None:
        return
    left, top = box[0], box[1]
    k = SUPERSAMPLE
    mask = Image.new("L", ((box[2] - box[0]) * k, (box[3] - box[1]) * k), 0)
    _draw_shape(ImageDraw.Draw(mask), item, k, left, top, 255)
    mask = mask.resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS)
    if item.kind == "highlight":
        mask = mask.point(lambda v: int(v * HIGHLIGHT_ALPHA))
    layer = Image.new("RGBA", mask.size, hex_to_rgb(item.colour) + (255,))
    layer.putalpha(mask)
    canvas.alpha_composite(layer, (left, top))
    if item.kind == "step":
        _stamp_number(canvas, item)


def _stamp_number(canvas: Image.Image, item: Item) -> None:
    x, y = item.points[0]
    r = step_radius(item)
    size = max(8, int(r * (1.2 if len(item.text) < 2 else 0.95)))
    font = load_font(size)
    d = ImageDraw.Draw(canvas)
    d.text((x, y), item.text, font=font, fill=hex_to_rgb(contrast_colour(item.colour)) + (255,),
           anchor="mm")


def _stamp_text(canvas: Image.Image, item: Item) -> None:
    if not item.text.strip():
        return
    font = load_font(text_size(item))
    x, y = item.points[0]
    d = ImageDraw.Draw(canvas)
    # a thin outline in the opposite tone keeps the words readable on any background
    outline = hex_to_rgb(contrast_colour(item.colour)) + (255,)
    stroke = max(1, int(round(text_size(item) / 14)))
    d.multiline_text((x, y), item.text, font=font, fill=hex_to_rgb(item.colour) + (255,),
                     stroke_width=stroke, stroke_fill=outline)


def _pixelate(canvas: Image.Image, item: Item) -> None:
    box = clamp_box(normalise(item.points[0], item.points[-1]), canvas.size)
    if box is None:
        return
    region = canvas.crop(box)
    block = max(4, int(round(item.width * 3)))
    small = region.resize((max(1, math.ceil(region.width / block)),
                           max(1, math.ceil(region.height / block))), Image.Resampling.BOX)
    canvas.paste(small.resize(region.size, Image.Resampling.NEAREST), box[:2])


def render_item(canvas: Image.Image, item: Item) -> None:
    """Paint one item onto canvas (RGBA) in place."""
    if item.kind == "pixelate":
        _pixelate(canvas, item)
    elif item.kind == "text":
        _stamp_text(canvas, item)
    elif item.kind in TOOLS:
        _stamp(canvas, item)


def render(base: Image.Image, items: Sequence[Item]) -> Image.Image:
    """The annotated picture at the base image's own resolution, as RGB."""
    canvas = base.convert("RGBA")
    for item in items:
        render_item(canvas, item)
    return canvas.convert("RGB")


def item_changes_pixels(item: Item, size: Tuple[int, int]) -> bool:
    """False for an item that would draw nothing (a zero-size drag, an empty box)."""
    if item.kind == "text":
        return bool(item.text.strip())
    if item.kind in ("rect", "ellipse", "arrow", "pixelate"):
        a, b = item.points[0], item.points[-1]
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 3:
            return False
        return item.kind != "pixelate" or clamp_box(normalise(a, b), size) is not None
    return True


# the document: items, crop, history ---------------------------------------------------------

class Document:
    """The screenshot being edited, the items on it, and the undo and redo history."""

    def __init__(self, image: Image.Image):
        self.base = image.convert("RGB")
        self.items: Tuple[Item, ...] = ()
        self._undo: List[Tuple[Image.Image, Tuple[Item, ...]]] = []
        self._redo: List[Tuple[Image.Image, Tuple[Item, ...]]] = []

    @property
    def size(self) -> Tuple[int, int]:
        return self.base.size

    @property
    def dirty(self) -> bool:
        return bool(self._undo)

    def _push(self) -> None:
        self._undo.append((self.base, self.items))
        self._redo.clear()

    def add(self, item: Item) -> bool:
        if not item_changes_pixels(item, self.size):
            return False
        self._push()
        self.items += (item,)
        return True

    def next_step_number(self) -> int:
        return 1 + sum(1 for item in self.items if item.kind == "step")

    def crop(self, box: Box) -> bool:
        """Keep only box (clamped to the image). Items move with the pixels; those left
        entirely outside still sit in the list, just off the picture."""
        box = clamp_box(box, self.size)
        if box is None or box == (0, 0) + self.size:
            return False
        self._push()
        dx, dy = box[0], box[1]
        self.base = self.base.crop(box)
        self.items = tuple(replace(item, points=tuple((x - dx, y - dy) for x, y in item.points))
                           for item in self.items)
        return True

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append((self.base, self.items))
        self.base, self.items = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append((self.base, self.items))
        self.base, self.items = self._redo.pop()
        return True

    def result(self) -> Image.Image:
        return render(self.base, self.items)
