"""Changes to a scanned page after the scan: quarter turns, straightening (deskew), and
brightness, contrast and Auto (whiter paper, darker ink). Pillow only, no numpy.

The scan on disk is never changed. A page carries an Edits record, and the edits are applied
when the page is opened for saving or OCR (Page.open) and, at screen size, for the view and
the thumbnails. The order is fixed: turn, straighten, then the tone (one lookup table)."""

from array import array
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageChops

MAX_SKEW = 10.0           # straighten pages tilted up to this many degrees either way
DETECT_SIZE = 1100        # long side of the copy the angle is measured on
MIN_GAIN = 1.5            # how far the sharpest angle must stand above the median one
Levels = Tuple[Tuple[int, int], ...]       # (black, white) per band, from auto_levels()


@dataclass
class Edits:
    turn: int = 0                  # quarter turns clockwise, 0-3
    angle: float = 0.0             # straightening, degrees counter-clockwise (PIL's rotate)
    straighten: bool = False       # angle came from detect_skew; off means angle is 0
    brightness: int = 0            # -100..100
    contrast: int = 0              # -100..100
    levels: Optional[Levels] = None   # Auto: set by auto_levels, None when Auto is off

    def geometry(self) -> bool:
        return bool(self.turn % 4) or (self.straighten and abs(self.angle) >= 0.05)

    def tone(self) -> bool:
        return bool(self.brightness or self.contrast or self.levels)

    def any(self) -> bool:
        return self.geometry() or self.tone()

    def copy(self) -> 'Edits':
        return Edits(self.turn, self.angle, self.straighten, self.brightness, self.contrast,
                     self.levels)


TURNS = {1: Image.Transpose.ROTATE_270, 2: Image.Transpose.ROTATE_180,
         3: Image.Transpose.ROTATE_90}          # PIL's names count counter-clockwise


def turned_size(size: Tuple[int, int], turn: int) -> Tuple[int, int]:
    return (size[1], size[0]) if turn % 2 else size


def apply_geometry(image: Image.Image, edits: Edits, fast: bool = False) -> Image.Image:
    """Turn, then straighten. The straightened page keeps its size; the corners that come
    in are white, like paper. fast: bilinear instead of bicubic (the live view)."""
    turn = edits.turn % 4
    if turn:
        image = image.transpose(TURNS[turn])
    if edits.straighten and abs(edits.angle) >= 0.05:
        resample = Image.Resampling.BILINEAR if fast else Image.Resampling.BICUBIC
        if image.mode == '1':
            # rotate the grey version smoothly, then back to black and white
            grey = image.convert('L').rotate(edits.angle, resample=resample, fillcolor=255)
            image = grey.point(lambda v: 255 if v >= 128 else 0, mode='1')
        else:
            white = (255,) * len(image.getbands()) if len(image.getbands()) > 1 else 255
            image = image.rotate(edits.angle, resample=resample, fillcolor=white)
    return image


def tone_table(edits: Edits, bands: int) -> Optional[List[int]]:
    """One lookup table for Auto's levels, then contrast around the middle, then brightness.
    None when there is nothing to do."""
    if not edits.tone():
        return None
    # contrast -100..100 -> factor 0.25..4 (0 is 1); brightness -100..100 -> -128..128
    factor = 4.0 ** (edits.contrast / 100.0)
    shift = edits.brightness * 1.28
    table: List[int] = []
    for band in range(bands):
        black, white = (edits.levels[min(band, len(edits.levels) - 1)]
                        if edits.levels else (0, 255))
        span = max(1, white - black)
        for v in range(256):
            x = (v - black) * 255.0 / span
            x = (x - 127.5) * factor + 127.5 + shift
            table.append(0 if x <= 0 else 255 if x >= 255 else int(x + 0.5))
    return table


def apply_tone(image: Image.Image, edits: Edits) -> Image.Image:
    if image.mode not in ('L', 'RGB'):
        return image                    # black and white pages have no tone to change
    table = tone_table(edits, len(image.getbands()))
    return image.point(table) if table else image


def apply(image: Image.Image, edits: Optional[Edits], fast: bool = False) -> Image.Image:
    if edits is None or not edits.any():
        return image
    return apply_tone(apply_geometry(image, edits, fast), edits)


# ─── Straightening ────────────────────────────────────────────

def _otsu(hist: Sequence[int]) -> int:
    total = sum(hist)
    if not total:
        return 128
    sum_all = sum(i * h for i, h in enumerate(hist))
    best, best_t, w_b, sum_b = -1.0, 128, 0, 0.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, best_t = between, t
    return best_t


def _ink(image: Image.Image) -> Optional[Image.Image]:
    """A small 'L' copy with ink 255 and paper 0, or None for a page with no ink to speak
    of (blank, or all dark)."""
    grey = image.convert('L') if image.mode != 'L' else image
    k = DETECT_SIZE / max(grey.size)
    if k < 1:
        grey = grey.resize((max(1, int(grey.width * k)), max(1, int(grey.height * k))),
                           Image.Resampling.BOX)
    hist = grey.histogram()
    level = max(60, min(210, _otsu(hist)))
    inked = sum(hist[:level + 1]) / max(1, grey.width * grey.height)
    if not 0.002 <= inked <= 0.6:
        return None
    return grey.point(lambda v: 255 if v <= level else 0)


def _edges(ink: Image.Image) -> Image.Image:
    """Where ink starts or stops going down the page: the tops and feet of lines of text,
    the edges of table rules and of squares. These line up in rows when the page is
    straight, for text and for a checkerboard alike (whose ink alone, row by row, is
    the same at every angle)."""
    return ImageChops.difference(ink, ImageChops.offset(ink, 0, 1))


def _sharpness(edges: Image.Image, angle: float) -> float:
    """How sharp the row profile is with the page turned by angle: edges that run straight
    across pile up in a few rows. Sum of squared differences between neighbouring rows,
    on the row means."""
    turned = (edges.rotate(angle, resample=Image.Resampling.NEAREST, fillcolor=0)
              if angle else edges)
    profile = turned.convert('F').resize((1, turned.height), Image.Resampling.BOX)
    rows = array('f', profile.tobytes())     # not getdata(), which Pillow is retiring
    return sum((b - a) * (b - a) for a, b in zip(rows, rows[1:]))


def _search(edges: Image.Image) -> Tuple[float, float, float]:
    """(best angle, its sharpness, the median sharpness of the 1° steps): 1° steps, then
    0.1° around the best. Lines of text, rules and grids give one sharp peak well above
    the median; a photo or noise give none."""
    limit = int(MAX_SKEW + 1)
    scores = {a: _sharpness(edges, float(a)) for a in range(-limit, limit + 1)}
    coarse = max(scores, key=scores.get)
    best_a, best_s = float(coarse), scores[coarse]
    for tenth in range(-9, 10):
        a = round(coarse + tenth / 10.0, 1)
        if tenth == 0 or abs(a) > limit:
            continue
        s = _sharpness(edges, a)
        if s > best_s:
            best_a, best_s = a, s
    return best_a, best_s, sorted(scores.values())[len(scores) // 2]


def detect_skew(image: Image.Image) -> Optional[float]:
    """The angle (degrees, counter-clockwise, for PIL's rotate) that makes the lines of the
    page run straight. 0.0 for a page that is already straight; None when there is nothing
    to go by (a blank page, noise). Lines are looked for across the page and, for a page
    scanned sideways, down it (a quarter turn doesn't change the angle); the direction with
    the sharper lines wins."""
    ink = _ink(image)
    if ink is None:
        return None
    across = _search(_edges(ink))
    down = _search(_edges(ink.transpose(Image.Transpose.ROTATE_90)))
    angle, best, median = max(across, down, key=lambda r: r[1])
    # no clear peak, or at the edge of the search: don't guess
    if best < median * MIN_GAIN or abs(angle) > MAX_SKEW + 0.5:
        return None
    return 0.0 if abs(angle) < 0.05 else angle


# ─── Auto: whiter paper ───────────────────────────────────────

def _band_levels(hist: Sequence[int]) -> Tuple[int, int]:
    """(black, white) for one band of a document: white is just below where the paper's
    peak starts, so the paper and its grain become white; black is the darkest 0.5 %."""
    total = sum(hist) or 1
    smooth = [sum(hist[max(0, i - 2):i + 3]) for i in range(256)]
    peak = max(range(96, 256), key=lambda i: smooth[i])
    white = peak
    while white > 96 and smooth[white - 1] > smooth[peak] * 0.25:
        white -= 1
    white = max(white, 128)
    seen, black = 0, 0
    for i in range(256):
        seen += hist[i]
        if seen >= total * 0.005:
            black = i
            break
    black = min(black, white // 2, 96)
    return black, white


def auto_levels(image: Image.Image) -> Optional[Levels]:
    """Levels that make a document's paper white and its ink dark. Each colour band gets its
    own white, so yellowed or tinted paper becomes white too. None for black and white."""
    if image.mode not in ('L', 'RGB'):
        return None
    small = image
    k = 600 / max(image.size)
    if k < 1:
        small = image.resize((max(1, int(image.width * k)), max(1, int(image.height * k))),
                             Image.Resampling.BOX)
    hist = small.histogram()
    return tuple(_band_levels(hist[i * 256:(i + 1) * 256])
                 for i in range(len(small.getbands())))


# ─── The live view ────────────────────────────────────────────

def fit(image: Image.Image, box: Tuple[int, int]) -> Image.Image:
    """The image scaled to fit box (w, h), as RGB for the screen."""
    iw, ih = image.size
    k = min(box[0] / iw, box[1] / ih)
    w, h = max(1, int(iw * k)), max(1, int(ih * k))
    scaled = image.resize((w, h), Image.Resampling.BILINEAR if k < 1 else
                          Image.Resampling.NEAREST)
    return scaled.convert('RGB') if scaled.mode != 'RGB' else scaled


def preview(view: Image.Image, edits: Edits, box: Tuple[int, int]) -> Image.Image:
    """What the window shows for a page: its screen-sized copy turned and straightened,
    scaled to the view, then toned. Toning after scaling keeps a slider drag cheap."""
    shown = fit(apply_geometry(view, edits, fast=True), box)
    return apply_tone(shown, edits)
