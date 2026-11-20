"""The pages of the document being scanned, and saving them: one PDF (written here, a page
at a time, so a long 600 dpi document never sits in memory at once), a searchable PDF made by
tesseract, or one PNG or JPG per page."""

import io
import os
import re
import shutil
import subprocess
import threading
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Sequence

from PIL import Image

from . import APP_NAME, JPEG_QUALITY, JPEG_QUALITY_FILE, VERSION
from .adjust import Edits, apply, turned_size
from .core import NO_WINDOW, Tesseract, log

Progress = Callable[[float, str], None]       # fraction done, page "2/5"


class Cancelled(Exception):
    pass


class SaveError(Exception):
    pass


@dataclass
class Page:
    path: str            # the kept scan in this window's cache folder (.pnm, or .png for B&W)
    width: int
    height: int
    dpi: float
    mode: str            # 'color', 'gray', 'bw'
    view_path: str = ''  # a screen-sized JPEG of it (work.make_view)
    edits: Edits = field(default_factory=Edits)   # turn, straighten, tone (adjust.py)
    skew: Optional[float] = None    # the measured straightening angle (work.straighten)
    measured: bool = False          # skew has been measured (None then: nothing to go by)

    def open(self, edited: bool = True) -> Image.Image:
        """The page as it will be saved: the scan with its edits applied. What is on disk
        stays as the scanner sent it."""
        image = Image.open(self.path)
        image.load()
        if image.mode not in ('1', 'L', 'RGB'):
            image = image.convert('RGB')
        if edited and self.edits.any():
            done = apply(image, self.edits)
            if done is not image:
                image.close()
            image = done
        return image

    @property
    def size(self):
        """Width and height in pixels as saved (a quarter turn swaps them)."""
        return turned_size((self.width, self.height), self.edits.turn)

    @property
    def size_mm(self):
        w, h = self.size
        return (w / self.dpi * 25.4, h / self.dpi * 25.4)

    def discard(self) -> None:
        for path in (self.path, self.view_path):
            if path:
                _remove(path)


def _check(cancel: Optional[threading.Event]) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _part(path: str) -> str:
    """A hidden file next to the target; it is renamed over the target only when complete."""
    folder, name = os.path.split(path)
    return os.path.join(folder, f".{name}.part")


# ─── PDF ──────────────────────────────────────────────────────

def pdf_text(value: str) -> bytes:
    """A PDF text string: UTF-16BE with a byte order mark, as hex, so any name works."""
    return b'<FEFF' + value.encode('utf-16-be').hex().upper().encode() + b'>'


def pdf_date(when: datetime) -> str:
    when = when.astimezone()
    offset = when.utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign = '+' if minutes >= 0 else '-'
    minutes = abs(minutes)
    return f"D:{when:%Y%m%d%H%M%S}{sign}{minutes // 60:02d}'{minutes % 60:02d}'"


def encode_for_pdf(image: Image.Image):
    """(data, filter, colour space, bits per component) for one page image."""
    if image.mode == '1':
        # rows are packed and padded to a byte, as PDF wants; 1 is white in both
        return zlib.compress(image.tobytes(), 6), b'/FlateDecode', b'/DeviceGray', 1
    if image.mode not in ('L', 'RGB'):
        image = image.convert('RGB')
    buf = io.BytesIO()
    image.save(buf, format='JPEG', quality=JPEG_QUALITY)
    space = b'/DeviceGray' if image.mode == 'L' else b'/DeviceRGB'
    return buf.getvalue(), b'/DCTDecode', space, 8


class PdfWriter:
    """A small PDF 1.4 writer: one full-page image per page, nothing else."""

    def __init__(self, f, title: str = ''):
        self.f = f
        self.offsets = {}
        self.kids: List[int] = []
        self.next_id = 3                     # 1 catalog, 2 page tree
        self.title = title
        self._write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')

    def _write(self, data: bytes) -> None:
        self.f.write(data)

    def _obj(self, num: int, body: bytes, stream: Optional[bytes] = None) -> None:
        self.offsets[num] = self.f.tell()
        self._write(f"{num} 0 obj\n".encode() + body)
        if stream is not None:
            self._write(b'\nstream\n' + stream + b'\nendstream')
        self._write(b'\nendobj\n')

    def _new(self) -> int:
        num = self.next_id
        self.next_id += 1
        return num

    def add_image_page(self, image: Image.Image, dpi: float) -> None:
        data, filt, space, bpc = encode_for_pdf(image)
        w_px, h_px = image.size
        w_pt, h_pt = w_px * 72.0 / dpi, h_px * 72.0 / dpi
        img, content, page = self._new(), self._new(), self._new()
        self._obj(img, b'<< /Type /XObject /Subtype /Image /Width %d /Height %d '
                       b'/ColorSpace %s /BitsPerComponent %d /Filter %s /Length %d >>'
                  % (w_px, h_px, space, bpc, filt, len(data)), data)
        draw = b'q\n%.3f 0 0 %.3f 0 0 cm\n/Im0 Do\nQ' % (w_pt, h_pt)
        self._obj(content, b'<< /Length %d >>' % len(draw), draw)
        self._obj(page, b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.3f %.3f] '
                        b'/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>'
                  % (w_pt, h_pt, img, content))
        self.kids.append(page)

    def close(self) -> None:
        kids = b' '.join(b'%d 0 R' % k for k in self.kids)
        self._obj(2, b'<< /Type /Pages /Kids [%s] /Count %d >>' % (kids, len(self.kids)))
        self._obj(1, b'<< /Type /Catalog /Pages 2 0 R >>')
        info = self._new()
        fields = b'/Producer %s /Creator %s /CreationDate (%s)' % (
            pdf_text(f"{APP_NAME} {VERSION}"), pdf_text(APP_NAME),
            pdf_date(datetime.now()).encode())
        if self.title:
            fields += b' /Title ' + pdf_text(self.title)
        self._obj(info, b'<< ' + fields + b' >>')
        xref = self.f.tell()
        size = self.next_id
        self._write(b'xref\n0 %d\n0000000000 65535 f \n' % size)
        for num in range(1, size):
            self._write(b'%010d 00000 n \n' % self.offsets[num])
        self._write(b'trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n'
                    % (size, info, xref))


def save_pdf(pages: Sequence[Page], path: str, title: str = '',
             progress: Optional[Progress] = None,
             cancel: Optional[threading.Event] = None) -> str:
    part = _part(path)
    try:
        with open(part, 'wb') as f:
            writer = PdfWriter(f, title)
            for i, page in enumerate(pages):
                _check(cancel)
                if progress:
                    progress(i / len(pages), f"{i + 1}/{len(pages)}")
                with page.open() as image:
                    writer.add_image_page(image, page.dpi)
            writer.close()
        _check(cancel)
        os.replace(part, path)
    except BaseException:
        _remove(part)
        raise
    if progress:
        progress(1.0, f"{len(pages)}/{len(pages)}")
    return path


# ─── One image per page ───────────────────────────────────────

def save_image(page: Page, path: str, fmt: str) -> None:
    part = _part(path)
    try:
        with page.open() as image:
            dpi = (round(page.dpi), round(page.dpi))
            if fmt == 'jpg':
                (image if image.mode != '1' else image.convert('L')).save(
                    part, format='JPEG', quality=JPEG_QUALITY_FILE, dpi=dpi)
            else:
                image.save(part, format='PNG', dpi=dpi, compress_level=6)
        os.replace(part, path)
    except BaseException:
        _remove(part)
        raise


def save_images(pages: Sequence[Page], paths: Sequence[str], fmt: str,
                progress: Optional[Progress] = None,
                cancel: Optional[threading.Event] = None) -> List[str]:
    done = []
    for i, (page, path) in enumerate(zip(pages, paths)):
        _check(cancel)
        if progress:
            progress(i / len(pages), f"{i + 1}/{len(pages)}")
        save_image(page, path, fmt)
        done.append(path)
    if progress:
        progress(1.0, f"{len(pages)}/{len(pages)}")
    return done


# ─── Searchable PDF (tesseract) ───────────────────────────────

def save_ocr_pdf(pages: Sequence[Page], path: str, lang: str, tesseract: Tesseract,
                 work_dir: str, progress: Optional[Progress] = None,
                 cancel: Optional[threading.Event] = None) -> str:
    """tesseract reads every page and writes one PDF: the page images with the text it found
    laid invisibly over them, so the PDF can be searched and the text copied."""
    if not tesseract.found:
        raise SaveError("tesseract is not installed")
    folder = os.path.join(work_dir, f"ocr-{int(time.time() * 1000)}")
    os.makedirs(folder, exist_ok=True)
    inputs = []
    try:
        for i, page in enumerate(pages):
            _check(cancel)
            if progress:
                progress(0.15 * i / len(pages), f"{i + 1}/{len(pages)}")
            dpi = (round(page.dpi), round(page.dpi))
            with page.open() as image:
                if image.mode == '1':
                    target = os.path.join(folder, f"page-{i + 1:04d}.png")
                    image.save(target, format='PNG', dpi=dpi, compress_level=1)
                else:
                    # tesseract puts a JPEG into the PDF as it is, without encoding it again
                    target = os.path.join(folder, f"page-{i + 1:04d}.jpg")
                    image.save(target, format='JPEG', quality=JPEG_QUALITY, dpi=dpi)
            inputs.append(target)
        listing = os.path.join(folder, 'pages.txt')
        with open(listing, 'w', encoding='utf-8') as f:
            f.write('\n'.join(inputs) + '\n')
        base = os.path.join(folder, 'out')
        cmd = [tesseract.cmd, listing, base, '-l', lang, 'pdf']
        log.info("run: %s", ' '.join(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                creationflags=NO_WINDOW)
        stop = threading.Event()

        def watch_cancel():
            while not stop.is_set():
                if cancel is not None and cancel.is_set() and proc.poll() is None:
                    proc.kill()
                    return
                time.sleep(0.1)

        threading.Thread(target=watch_cancel, daemon=True).start()
        err = []
        assert proc.stderr
        try:
            for raw in iter(proc.stderr.readline, b''):
                line = raw.decode('utf-8', 'replace').strip()
                m = re.match(r'Page (\d+)', line)
                if m and progress:
                    n = int(m.group(1))
                    progress(0.15 + 0.85 * (n - 1) / len(pages), f"{n}/{len(pages)}")
                elif line:
                    err.append(line)
            code = proc.wait()
        finally:
            stop.set()
            proc.stderr.close()
        _check(cancel)
        made = base + '.pdf'
        if code != 0 or not os.path.isfile(made):
            log.error("tesseract exited %s: %s", code, '\n'.join(err[-10:]))
            raise SaveError(err[-1] if err else f"tesseract exited with {code}")
        # the cache and Documents can be on different drives: copy, then rename into place
        part = _part(path)
        try:
            shutil.copyfile(made, part)
            os.replace(part, path)
        except BaseException:
            _remove(part)
            raise
        if progress:
            progress(1.0, f"{len(pages)}/{len(pages)}")
        return path
    finally:
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            _remove(os.path.join(folder, name))
        try:
            os.rmdir(folder)
        except OSError:
            pass
