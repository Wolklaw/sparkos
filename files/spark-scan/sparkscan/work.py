"""Scanning a preview or pages into this window's cache folder. Used by the window (in a
worker thread) and by `spark-scan --scan-to` (no window). No Tk here."""

import itertools
import os
import shutil
import threading
from typing import Callable, List, Optional

from PIL import Image

from . import PREVIEW_DPI
from .core import log
from .document import Page
from .scanner import Caps, Job, Request, ScanError, command, finish_page

VIEW_SIZE = 1400            # long side of the copy each page is shown from
THUMB_SIZE = 132


class Session:
    """A folder of scanned pages. Pages stay on disk, not in memory, so a long document at
    600 dpi doesn't fill the RAM; the folder is removed when the window closes."""

    def __init__(self, folder: str):
        self.folder = folder
        self._ids = itertools.count(1)
        self.job: Optional[Job] = None
        self.lock = threading.Lock()

    def _stem(self, prefix: str) -> str:
        return os.path.join(self.folder, f"{prefix}-{next(self._ids):04d}")

    def cancel(self) -> None:
        with self.lock:
            job = self.job
        if job:
            job.cancel()

    def cancelled(self) -> bool:
        with self.lock:
            return bool(self.job and self.job.cancelled.is_set())

    def _run(self, cmd: List[str], on_progress, on_page=None) -> int:
        job = Job(cmd, on_progress)
        with self.lock:
            self.job = job
        try:
            return job.run(on_page)
        finally:
            with self.lock:
                self.job = None

    def preview(self, caps: Caps, mode: str = 'color',
                on_progress: Optional[Callable[[float, int], None]] = None
                ) -> Optional[Image.Image]:
        """The whole glass at low resolution, or None if cancelled."""
        req = Request(caps.device, caps.preview_resolution(PREVIEW_DPI), mode,
                      source='glass' if 'glass' in caps.sources else '')
        raw = self._stem('preview') + '.pnm'
        try:
            if self._run(command(caps, req, out=raw), on_progress) != 0:
                return None
            with Image.open(raw) as im:
                return im.convert('RGB')
        finally:
            try:
                os.remove(raw)
            except OSError:
                pass

    def scan(self, caps: Caps, req: Request,
             on_progress: Optional[Callable[[float, int], None]] = None,
             on_page: Optional[Callable[[Page], None]] = None,
             views: bool = True) -> List[Page]:
        """One page from the glass, or every sheet in the feeder. Each finished page goes to
        on_page as soon as it is ready. A cancelled feeder scan keeps the pages already
        finished."""
        pages: List[Page] = []
        dpi = caps.resolution(req.dpi) if (caps.resolutions or caps.res_range) else req.dpi

        def keep(raw: str, _n: int):
            path, w, h = finish_page(raw, req, caps, self._stem('page'))
            page = Page(path, w, h, dpi, req.mode)
            if views:
                make_view(page)
            pages.append(page)
            if on_page:
                on_page(page)

        feeder = req.source in ('feeder', 'duplex')
        if feeder:
            pattern = self._stem('feed') + '-%d.pnm'
            code = self._run(command(caps, req, batch=pattern), on_progress, keep)
        else:
            raw = self._stem('raw') + '.pnm'
            code = self._run(command(caps, req, out=raw), on_progress)
            if code == 0:
                keep(raw, 1)
            else:
                _remove_quietly(raw)
        if code != 0 and not pages and not feeder:
            log.info("scan cancelled")
        return pages

    def clear(self) -> None:
        shutil.rmtree(self.folder, ignore_errors=True)


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def make_view(page: Page) -> None:
    """A screen-sized JPEG next to the page, so showing a 600 dpi page is instant."""
    with Image.open(page.path) as im:
        if im.mode == '1':
            im = im.convert('L')
        elif im.mode not in ('L', 'RGB'):
            im = im.convert('RGB')
        # JPEG and PNM pages are reduced while they load where Pillow can
        im.thumbnail((VIEW_SIZE, VIEW_SIZE), Image.Resampling.BILINEAR, reducing_gap=2.0)
        view = os.path.splitext(page.path)[0] + '-view.jpg'
        im.save(view, format='JPEG', quality=88)
    page.view_path = view


def view_image(page: Page) -> Image.Image:
    path = page.view_path or page.path
    with Image.open(path) as im:
        im.load()
        return im.convert('RGB') if im.mode not in ('L', 'RGB') else im.copy()


__all__ = ['Session', 'ScanError', 'make_view', 'view_image', 'THUMB_SIZE']
