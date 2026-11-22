"""Thumbnails for photos and videos, made in the background and kept in the freedesktop
thumbnail cache (~/.cache/thumbnails), the same one Dolphin and Spark Media use, so a photo
seen in one of them is instant in the others.

Thumbnailer.request(path, mtime) queues a job; the newest requests go first (what's on screen
now matters more than what scrolled past). Results come back through a callback in the worker
thread; the window moves them to Tk's thread itself. Videos need GStreamer (in the SparkOS
image); without it they keep their icon."""

import hashlib
import os
import threading
from typing import Callable, Dict, List, Tuple
from urllib.parse import quote

from . import APP_NAME, THUMB_MAX_BYTES, VERSION
from .core import log
from .listing import THUMB_IMAGE, THUMB_VIDEO

SIZES = {'normal': 128, 'large': 256}
FAIL_DIR = f'{APP_NAME.lower().replace(" ", "-")}-{VERSION}'

try:
    from PIL import Image, ImageOps, PngImagePlugin
except ImportError:                       # thumbnails off; the rest works
    Image = None


def cache_root() -> str:
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    return os.path.join(base, 'thumbnails')


def file_uri(path: str) -> str:
    return 'file://' + quote(os.path.abspath(path), safe="/!$&'()*+,;=:@~-._")


def thumb_path(path: str, flavour: str = 'normal') -> str:
    digest = hashlib.md5(file_uri(path).encode('utf-8', 'surrogateescape')).hexdigest()
    return os.path.join(cache_root(), flavour, digest + '.png')


def fail_path(path: str) -> str:
    digest = hashlib.md5(file_uri(path).encode('utf-8', 'surrogateescape')).hexdigest()
    return os.path.join(cache_root(), 'fail', FAIL_DIR, digest + '.png')


def can_thumbnail(ext: str) -> bool:
    if Image is None:
        return False
    return ext in THUMB_IMAGE or (ext in THUMB_VIDEO and video_ok())


def in_cache_dir(path: str) -> bool:
    """Never thumbnail the thumbnail cache itself (the spec says so)."""
    return os.path.abspath(path).startswith(cache_root() + os.sep)


def cached(path: str, mtime: float, flavour: str = 'normal'):
    """The cached thumbnail if it's there and made from this version of the file."""
    if Image is None:
        return None
    for fl in ((flavour, 'large') if flavour == 'normal' else (flavour, 'x-large')):
        thumb = thumb_path(path, fl)
        try:
            with Image.open(thumb) as image:
                stored = image.info.get('Thumb::MTime')
                if stored is not None and int(float(stored)) != int(mtime):
                    continue
                image.load()
                out = image.copy()
            if fl != flavour:
                out.thumbnail((SIZES[flavour], SIZES[flavour]))
            return out
        except (OSError, ValueError, SyntaxError):
            continue
    return None


def failed_before(path: str, mtime: float) -> bool:
    try:
        with Image.open(fail_path(path)) as image:
            return int(float(image.info.get('Thumb::MTime', -1))) == int(mtime)
    except (OSError, ValueError, SyntaxError, AttributeError):
        return False


def _save(path: str, image, mtime: float, target: str) -> None:
    try:
        os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
        info = PngImagePlugin.PngInfo()
        info.add_text('Thumb::URI', file_uri(path))
        info.add_text('Thumb::MTime', str(int(mtime)))
        info.add_text('Software', APP_NAME)
        tmp = f'{target}.{os.getpid()}.{threading.get_ident()}.tmp'
        image.save(tmp, 'PNG', pnginfo=info)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except OSError as exc:
        log.debug("could not cache thumbnail for %s: %s", path, exc)


def _displayable(image):
    if image.mode in ('RGBA', 'RGB'):
        return image
    if image.mode in ('P', 'LA', 'PA') or 'transparency' in image.info:
        return image.convert('RGBA')
    return image.convert('RGB')


def make_image_thumb(path: str, size: int):
    with Image.open(path) as source:
        source.draft('RGB', (size * 2, size * 2))          # JPEG decodes at a fraction
        image = _displayable(ImageOps.exif_transpose(source))
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        return image


_GST = None
_GST_LOCK = threading.Lock()


def video_ok() -> bool:
    global _GST
    with _GST_LOCK:
        if _GST is None:
            try:
                import gi
                gi.require_version('Gst', '1.0')
                from gi.repository import Gst
                Gst.init(None)
                _GST = Gst if Gst.ElementFactory.find('playbin') else False
            except (ImportError, ValueError, Exception):    # noqa: BLE001
                _GST = False
    return bool(_GST)


def make_video_thumb(path: str, size: int, timeout: float = 8.0):
    """A frame from 10% into the video, through playbin's convert-sample."""
    if not video_ok():
        return None
    Gst = _GST
    second = 1_000_000_000
    pb = Gst.ElementFactory.make('playbin', None)
    pb.set_property('uri', file_uri(path))
    pb.set_property('audio-sink', Gst.ElementFactory.make('fakesink', None))
    pb.set_property('video-sink', Gst.ElementFactory.make('fakesink', None))
    pb.set_property('flags', 0x1)                          # video only
    bus = pb.get_bus()
    wait = int(timeout * second)
    try:
        pb.set_state(Gst.State.PAUSED)
        msg = bus.timed_pop_filtered(wait, Gst.MessageType.ASYNC_DONE | Gst.MessageType.ERROR)
        if msg is None or msg.type == Gst.MessageType.ERROR:
            return None
        ok, duration = pb.query_duration(Gst.Format.TIME)
        if ok and duration > 0:
            pb.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                           int(duration * 0.1))
            bus.timed_pop_filtered(wait, Gst.MessageType.ASYNC_DONE | Gst.MessageType.ERROR)
        caps = Gst.Caps.from_string(f'video/x-raw,format=RGB,width={size},pixel-aspect-ratio=1/1')
        sample = pb.emit('convert-sample', caps)
        if sample is None:
            return None
        s = sample.get_caps().get_structure(0)
        width, height = s.get_value('width'), s.get_value('height')
        buf = sample.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return None
        try:
            stride = len(info.data) // height
            image = Image.frombuffer('RGB', (width, height), bytes(info.data), 'raw', 'RGB',
                                     stride, 1).copy()
        finally:
            buf.unmap(info)
        image.thumbnail((size, size))
        return image
    finally:
        pb.set_state(Gst.State.NULL)


def make(path: str, ext: str, mtime: float, size_bytes: int, flavour: str = 'normal'):
    """The thumbnail, from the cache or made now (slow: call it in a worker). None when the
    file has none; that's remembered in the cache's fail folder."""
    if Image is None or in_cache_dir(path):
        return None
    image = cached(path, mtime, flavour)
    if image is not None:
        return image
    if failed_before(path, mtime):
        return None
    size = SIZES[flavour]
    image = None
    try:
        if ext in THUMB_IMAGE:
            if size_bytes > THUMB_MAX_BYTES:
                return None
            image = make_image_thumb(path, size)
        elif ext in THUMB_VIDEO:
            image = make_video_thumb(path, size)
    except Exception as exc:             # noqa: BLE001 - a broken file is no reason to stop
        log.debug("no thumbnail for %s: %s", path, exc)
        image = None
    if image is None:
        if Image is not None and os.path.exists(path):
            _save(path, Image.new('RGBA', (1, 1)), mtime, fail_path(path))
        return None
    _save(path, image, mtime, thumb_path(path, flavour))
    return image


class Thumbnailer:
    """Two worker threads; newest request first; each path asked for once at a time."""

    def __init__(self, deliver: Callable[[str, float, object], None], workers: int = 2):
        self.deliver = deliver
        self._lock = threading.Condition()
        self._queue: List[Tuple[str, str, float, int, str]] = []
        self._pending: Dict[Tuple[str, str], bool] = {}
        self._stop = False
        self._threads = [threading.Thread(target=self._work, name=f'thumbs-{i}', daemon=True)
                         for i in range(workers)]
        for t in self._threads:
            t.start()

    def request(self, path: str, ext: str, mtime: float, size_bytes: int,
                flavour: str = 'normal') -> None:
        with self._lock:
            key = (path, flavour)
            if key in self._pending:
                return
            self._pending[key] = True
            self._queue.append((path, ext, mtime, size_bytes, flavour))
            self._lock.notify()

    def forget_queued(self) -> None:
        """Drop what hasn't started: the folder changed."""
        with self._lock:
            for path, _e, _m, _s, flavour in self._queue:
                self._pending.pop((path, flavour), None)
            self._queue.clear()

    def stop(self) -> None:
        with self._lock:
            self._stop = True
            self._queue.clear()
            self._lock.notify_all()

    def _work(self) -> None:
        while True:
            with self._lock:
                while not self._queue and not self._stop:
                    self._lock.wait()
                if self._stop:
                    return
                path, ext, mtime, size_bytes, flavour = self._queue.pop()    # newest first
            image = make(path, ext, mtime, size_bytes, flavour)
            with self._lock:
                self._pending.pop((path, flavour), None)
            if image is not None:
                try:
                    self.deliver(path, mtime, image)
                except Exception:        # noqa: BLE001
                    log.exception("thumbnail delivery")
