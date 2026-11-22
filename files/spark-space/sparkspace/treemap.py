"""Squarified treemap layout (Bruls, Huizing and van Wijk, 2000): rectangles whose areas match
the sizes, kept as close to square as the order allows, so small items stay clickable."""

from typing import List, Sequence, Tuple

Rect = Tuple[float, float, float, float]          # x, y, width, height


def _worst(row: Sequence[float], side: float) -> float:
    s = sum(row)
    if s <= 0 or side <= 0:
        return float('inf')
    hi, lo = max(row), min(row)
    side2, s2 = side * side, s * s
    return max(side2 * hi / s2, s2 / (side2 * lo)) if lo > 0 else float('inf')


def squarify(sizes: Sequence[float], x: float, y: float, w: float, h: float) -> List[Rect]:
    """One rectangle per size, in the same order. Sizes should be sorted biggest first (the
    layout still covers the area otherwise, just with less square shapes). Zero and negative
    sizes get an empty rectangle."""
    out: List[Rect] = [(x, y, 0.0, 0.0)] * len(sizes)
    total = float(sum(s for s in sizes if s > 0))
    if total <= 0 or w <= 0 or h <= 0:
        return out
    scale = w * h / total
    items = [(i, s * scale) for i, s in enumerate(sizes) if s > 0]
    cx, cy, cw, ch = x, y, float(w), float(h)
    k = 0
    while k < len(items):
        side = min(cw, ch)
        row = [items[k][1]]
        j = k + 1
        while j < len(items):
            trial = row + [items[j][1]]
            if _worst(trial, side) <= _worst(row, side):
                row = trial
                j += 1
            else:
                break
        rowsum = area = sum(row)
        if j >= len(items):
            area = cw * ch if cw * ch > 0 else area      # the last row fills what's left
        if cw >= ch:                                   # lay the row down the left side
            rw = area / ch if ch > 0 else 0
            yy = cy
            for n, (idx, a) in enumerate(items[k:j]):
                rh = a / rowsum * ch
                if n == j - k - 1:
                    rh = cy + ch - yy
                out[idx] = (cx, yy, rw, rh)
                yy += rh
            cx += rw
            cw -= rw
        else:                                          # lay the row along the top
            rh = area / cw if cw > 0 else 0
            xx = cx
            for n, (idx, a) in enumerate(items[k:j]):
                rw = a / rowsum * cw
                if n == j - k - 1:
                    rw = cx + cw - xx
                out[idx] = (xx, cy, rw, rh)
                xx += rw
            cy += rh
            ch -= rh
        cw, ch = max(cw, 0.0), max(ch, 0.0)
        k = j
    return out
