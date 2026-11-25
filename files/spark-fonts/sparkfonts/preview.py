"""Drawing fonts with Pillow, off the window's thread.

Tk can only draw a font that is installed, by family name. A preview has to work for a file that
is not installed (a download, a font on the Windows drive), so every preview is drawn here from
the file: ImageFont.truetype with the face index (collections) and the named instance
(variable fonts), saved as PNG bytes that Tk takes as PhotoImage(data=...). Nothing is cached on
disk. Results are cached in memory per (file, face, size, text, colours).

A Renderer owns one worker thread. The window calls request() and polls() from its own thread;
the callback runs on the window's thread."""

import collections
import io
import queue
import threading
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

from . import fcdata
from .core import log, run

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:                                   # the self-test says so
    Image = ImageDraw = ImageFont = None

CACHE_ITEMS = 400
SAMPLE = "Sphinx of black quartz, judge my vow"
PANGRAMS = {
    'en': "Sphinx of black quartz, judge my vow",
    'fr': "Portez ce vieux whisky au juge blond qui fume",
}
DIGITS = "0123456789  ÀÉÈÊÇ àéèêç « » ? ! & @ % €"


def available() -> bool:
    return Image is not None


def open_font(path: str, index: int, size: int, instance: int = 0):
    """An ImageFont for one face. instance is fontconfig's: 0 = the font itself, n = the n-th
    named instance of a variable font."""
    font = ImageFont.truetype(path, size, index=index)
    if instance:
        try:
            names = font.get_variation_names()
            font.set_variation_by_name(names[instance - 1])
        except (OSError, ValueError, IndexError, AttributeError) as exc:
            log.info("%s: instance %d not set: %s", path, instance, exc)
    return font


def open_face(face: 'fcdata.Face', size: int):
    return open_font(face.path, face.face_index, size, face.instance)


def _png(img) -> bytes:
    out = io.BytesIO()
    img.save(out, 'PNG', compress_level=1)
    return out.getvalue()


def wrap(font, text: str, width: int) -> List[str]:
    """Lines of text that fit width (breaking at spaces; a long word is cut by letters)."""
    lines: List[str] = []
    for para in text.split('\n'):
        line = ''
        for word in para.split(' '):
            trial = word if not line else line + ' ' + word
            if font.getlength(trial) <= width:
                line = trial
                continue
            if line:
                lines.append(line)
            line = word
            while line and font.getlength(line) > width and len(line) > 1:
                cut = len(line) - 1
                while cut > 1 and font.getlength(line[:cut]) > width:
                    cut -= 1
                lines.append(line[:cut])
                line = line[cut:]
        lines.append(line)
    return lines


def draw_text(face: 'fcdata.Face', text: str, size: int, width: int, fg: str, bg: str,
              max_lines: int = 4) -> Tuple[bytes, int]:
    """(PNG bytes, height) of text in the face, wrapped to width."""
    font = open_face(face, size)
    ascent, descent = font.getmetrics()
    lead = max(1, int((ascent + descent) * 1.12))
    lines = wrap(font, text or ' ', max(16, width - 4))[:max_lines]
    height = lead * len(lines) + 6
    img = Image.new('RGB', (max(16, width), height), bg)
    pen = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        pen.text((2, 3 + i * lead), line, font=font, fill=fg)
    return _png(img), height


# ─── Characters ──────────────────────────────────────────────

def charset(path: str, index: int = 0) -> List[int]:
    """The code points a face has, from fc-query's charset ranges."""
    code, out, _err = run(['fc-query', '-i', str(index & 0xffff), '--format', '%{charset}\n',
                           path], timeout=30)
    if code != 0:
        return []
    chars: List[int] = []
    for part in out.split():
        lo, _, hi = part.partition('-')
        try:
            a, b = int(lo, 16), int(hi or lo, 16)
        except ValueError:
            continue
        if b - a > 0x20000:
            continue
        chars.extend(c for c in range(a, b + 1) if _printable(c))
        if len(chars) > 300000:
            break
    return chars


def _printable(c: int) -> bool:
    if c < 0x20 or 0x7f <= c < 0xa0 or 0xd800 <= c < 0xe000:
        return False
    return unicodedata.category(chr(c)) not in ('Cc', 'Cs', 'Cn', 'Zl', 'Zp')


def char_name(c: int) -> str:
    try:
        return unicodedata.name(chr(c)).title()
    except ValueError:
        return ''


def parse_char_query(text: str) -> Optional[int]:
    """'é', 'U+00E9', 'u+e9' or '0xe9' -> a code point; None when it isn't one."""
    text = text.strip()
    if not text:
        return None
    if len(text) == 1:
        return ord(text)
    low = text.lower()
    for prefix in ('u+', '0x', '\\u'):
        if low.startswith(prefix):
            try:
                return int(low[len(prefix):], 16)
            except ValueError:
                return None
    try:
        return ord(unicodedata.lookup(text))
    except KeyError:
        return None


def grid_image(face: 'fcdata.Face', chars: List[int], cell: int, columns: int, fg: str,
               bg: str, edge: str, mark: Optional[int] = None,
               mark_fill: str = '#12292c') -> Tuple[bytes, int, int]:
    """(PNG bytes, width, height) of a grid of cells, one character each, with a hairline
    between cells; the cell of mark is filled."""
    font = open_face(face, max(8, int(cell * 0.5)))
    rows = max(1, -(-len(chars) // columns))
    w, h = columns * cell + 1, rows * cell + 1
    img = Image.new('RGB', (w, h), bg)
    pen = ImageDraw.Draw(img)
    for i, c in enumerate(chars):
        x, y = (i % columns) * cell, (i // columns) * cell
        if c == mark:
            pen.rectangle([x + 1, y + 1, x + cell - 1, y + cell - 1], fill=mark_fill)
        pen.text((x + cell / 2, y + cell / 2), chr(c), font=font, fill=fg, anchor='mm')
    for i in range(columns + 1):
        pen.line([(i * cell, 0), (i * cell, h)], fill=edge)
    for j in range(rows + 1):
        pen.line([(0, j * cell), (w, j * cell)], fill=edge)
    return _png(img), w, h


# ─── The worker ──────────────────────────────────────────────

class Renderer:
    """Draws on a thread. request(key, fn, done): fn() -> result runs on the thread (once per
    key while cached); done(result) runs from polls() on the window's thread. A newer request
    for the same slot makes an older, unstarted one stale."""

    def __init__(self):
        self.jobs: 'queue.Queue' = queue.Queue()
        self.results: 'queue.Queue' = queue.Queue()
        self.cache: 'collections.OrderedDict[tuple, object]' = collections.OrderedDict()
        self.latest: Dict[str, object] = {}
        self.lock = threading.Lock()
        self.stopped = False
        self.thread = threading.Thread(target=self._work, daemon=True, name='spark-fonts-draw')
        self.thread.start()

    def request(self, slot: str, key: tuple, fn: Callable[[], object],
                done: Callable[[object], None]) -> None:
        token = object()
        with self.lock:
            self.latest[slot] = token
            if key in self.cache:
                self.cache.move_to_end(key)
                self.results.put((slot, token, done, self.cache[key]))
                return
        self.jobs.put((slot, token, key, fn, done))

    def _work(self) -> None:
        while not self.stopped:
            try:
                slot, token, key, fn, done = self.jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.lock:
                if self.latest.get(slot) is not token:      # asked again meanwhile
                    continue
            try:
                result = fn()
            except Exception as exc:                        # noqa: BLE001 (a bad font file)
                log.info("draw failed: %s", exc)
                result = None
            with self.lock:
                if result is not None:
                    self.cache[key] = result
                    while len(self.cache) > CACHE_ITEMS:
                        self.cache.popitem(last=False)
            self.results.put((slot, token, done, result))

    def poll(self, limit: int = 24) -> int:
        """Hand finished results to their callbacks. Call from the window's thread."""
        n = 0
        while n < limit:
            try:
                slot, token, done, result = self.results.get_nowait()
            except queue.Empty:
                break
            n += 1
            with self.lock:
                stale = self.latest.get(slot) is not token
            if not stale:
                done(result)
        return n

    def close(self) -> None:
        self.stopped = True
