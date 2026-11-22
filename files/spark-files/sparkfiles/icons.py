"""File icons, drawn here in the house style (outlines in the palette's colours on the dark
panels) rather than taken from an icon theme, so the app looks the same on any desktop.
Each kind is drawn once per size with Pillow and kept as a Tk image."""

import base64
import io
from typing import Dict, Tuple

import tkinter as tk

try:
    from PIL import Image, ImageDraw
    try:
        from PIL import ImageTk
    except ImportError:
        ImageTk = None
except ImportError:
    Image = ImageDraw = ImageTk = None

from .widgets import T

COLOURS = {
    'folder': T["accent"], 'file': T["muted"], 'image': T["gold"], 'video': T["pink"],
    'audio': '#b9a6ff', 'archive': '#f0a671', 'document': '#8ec9ff', 'code': '#52e8a4',
    'program': T["pink"], 'drive': T["accent"], 'usb': T["accent"], 'trash': T["muted"],
    'home': T["accent"], 'desktop': T["accent"], 'download': T["accent"], 'game': T["accent"],
    'pin': T["gold"], 'broken': T["dim"],
}


def to_photo(master, image) -> tk.PhotoImage:
    """A Pillow image as a Tk image, with or without Pillow's Tk module."""
    if ImageTk is not None:
        return ImageTk.PhotoImage(image, master=master)
    buf = io.BytesIO()
    image.save(buf, 'PNG')
    return tk.PhotoImage(master=master, data=base64.b64encode(buf.getvalue()).decode('ascii'))


def _draw(kind: str, size: int, link: bool = False):
    k = 4                                            # drawn 4x, then scaled down: smooth edges
    s = size * k
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = COLOURS.get(kind, T["muted"])
    w = max(k, round(s / 14))
    u = s / 24.0

    def P(*pts):
        return [v * u for v in pts]

    def line(*pts):
        d.line(P(*pts), fill=c, width=w, joint='curve')

    if kind in ('folder', 'home', 'desktop', 'download', 'game', 'pin'):
        d.polygon(P(2, 5, 9, 5, 11, 7.5, 22, 7.5, 22, 20, 2, 20), outline=c, width=w,
                  fill=_fade(c, 0.16))
        if kind == 'home':
            line(8, 17, 8, 13, 12, 10, 16, 13, 16, 17)
        elif kind == 'download':
            line(12, 10, 12, 17)
            line(9, 14.5, 12, 17, 15, 14.5)
        elif kind == 'desktop':
            d.rectangle(P(7, 11, 17, 16), outline=c, width=w)
        elif kind == 'game':
            line(8, 13.5, 11, 13.5)
            line(9.5, 12, 9.5, 15)
            d.ellipse(P(14, 12, 16, 14), fill=c)
        elif kind == 'pin':
            line(12, 10.5, 12, 17)
            d.ellipse(P(10, 9, 14, 13), fill=c)
    elif kind in ('drive', 'usb'):
        d.rectangle(P(2.5, 7, 21.5, 17), outline=c, width=w, fill=_fade(c, 0.14))
        d.ellipse(P(16.5, 11, 18.5, 13), fill=c)
        if kind == 'usb':
            line(5, 12, 12, 12)
    elif kind == 'trash':
        line(5, 6.5, 19, 6.5)
        line(10, 6.5, 10, 4, 14, 4, 14, 6.5)
        d.polygon(P(6.5, 6.5, 7.5, 20.5, 16.5, 20.5, 17.5, 6.5), outline=c, width=w)
    else:
        d.polygon(P(5, 2.5, 14.5, 2.5, 19, 7, 19, 21.5, 5, 21.5), outline=c, width=w,
                  fill=_fade(c, 0.10))
        line(14.5, 2.5, 14.5, 7, 19, 7)
        if kind == 'image':
            d.polygon(P(7.5, 18.5, 11, 13.5, 13.5, 16.5, 15, 15, 16.5, 18.5), fill=c)
            d.ellipse(P(8, 9, 10.5, 11.5), fill=c)
        elif kind == 'video':
            d.polygon(P(9.5, 11, 9.5, 18, 15.5, 14.5), fill=c)
        elif kind == 'audio':
            line(10, 18, 10, 11, 15.5, 10, 15.5, 16.5)
            d.ellipse(P(7.5, 16.5, 10.5, 19), fill=c)
            d.ellipse(P(13, 15, 16, 17.5), fill=c)
        elif kind == 'archive':
            for y in (5, 8, 11, 14):
                line(11, y, 13, y)
            d.rectangle(P(10, 15.5, 14, 19), outline=c, width=w)
        elif kind == 'document':
            for y, x1 in ((11, 16), (14, 16), (17, 13)):
                line(8, y, x1, y)
        elif kind == 'code':
            line(10, 11, 8, 14, 10, 17)
            line(14, 11, 16, 14, 14, 17)
        elif kind == 'program':
            line(8.5, 11, 11, 13.5, 8.5, 16)
            line(12.5, 17, 16, 17)
        elif kind == 'broken':
            line(8, 11, 16, 18)
            line(16, 11, 8, 18)
    if link:
        a = T["ch_b"]
        d.rectangle(P(0, 15, 9, 24), fill=T["bg"])
        d.line(P(2, 22, 7, 17), fill=a, width=w)
        d.line(P(3.5, 17, 7, 17, 7, 20.5), fill=a, width=w)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _fade(colour: str, alpha: float) -> Tuple[int, int, int, int]:
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16), int(255 * alpha))


class Icons:
    def __init__(self, master):
        self.master = master
        self._cache: Dict[Tuple[str, int, bool], tk.PhotoImage] = {}

    def get(self, kind: str, size: int, link: bool = False):
        key = (kind, size, link)
        image = self._cache.get(key)
        if image is None:
            if Image is None:
                return None
            image = to_photo(self.master, _draw(kind, size, link))
            self._cache[key] = image
        return image
