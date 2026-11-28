"""The desktop: one background-layer window per monitor showing the wallpaper. No icons.

The image is decoded once, at the size the largest monitor needs (8 bits per channel), and the
same texture is shared by every monitor. Handing each Gtk.Picture the file instead decodes it
at full size once per monitor: SparkOS's own 3840x2160 16-bit PNG is 66 MB each time."""

import ctypes
import logging
import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from . import config, layer  # noqa: E402

log = logging.getLogger('spark-shell')

FIT = {
    'fill': Gtk.ContentFit.COVER,
    'fit': Gtk.ContentFit.CONTAIN,
    'stretch': Gtk.ContentFit.FILL,
    'center': Gtk.ContentFit.SCALE_DOWN,
}


def decode_size(image, screens, mode):
    """The (width, height) to decode an image of size `image` at, for monitors whose pixel sizes
    are `screens`: just big enough for the most demanding one, never bigger than the file.
    'center' shows the image at its own size, so it keeps the file's size."""
    iw, ih = image
    if mode == 'center' or not screens or iw <= 0 or ih <= 0:
        return iw, ih
    s = 0.0
    for sw, sh in screens:
        s = max(s, sw / iw, sh / ih)
    s = min(s, 1.0)
    return max(1, round(iw * s)), max(1, round(ih * s))


_cache = {}     # (path, mtime, size) -> Gdk.Texture; holds only the texture in use


def texture_for(path, screens, mode):
    """One shared texture for the wallpaper, or None if the file can't be read."""
    if not path:
        return None
    try:
        mtime = os.stat(path).st_mtime_ns
        fmt, iw, ih = GdkPixbuf.Pixbuf.get_file_info(path)
        if fmt is None:
            raise GLib.Error('not an image')
        size = decode_size((iw, ih), screens, mode)
        key = (path, mtime, size)
        if key not in _cache:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size[0], size[1], False)
            fmt = Gdk.MemoryFormat.R8G8B8A8 if pb.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
            texture = Gdk.MemoryTexture.new(pb.get_width(), pb.get_height(), fmt,
                                            pb.read_pixel_bytes(), pb.get_rowstride())
            del pb
            _cache.clear()
            _cache[key] = texture
            _trim()
        return _cache[key]
    except (GLib.Error, OSError) as e:
        log.warning('wallpaper %s: %s', path, e)
        return None


def _trim():
    """Give the decoder's scratch memory back to the system. glibc keeps freed heap for
    reuse, and decoding a big PNG frees tens of MB the shell never needs again."""
    try:
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except (OSError, AttributeError):
        pass


def screen_sizes(monitors):
    """Pixel sizes of the given Gdk.Monitors."""
    sizes = []
    for m in monitors:
        g = m.get_geometry()
        scale = m.get_scale() if hasattr(m, 'get_scale') else m.get_scale_factor()
        sizes.append((round(g.width * scale), round(g.height * scale)))
    return sizes


class Wallpaper(Gtk.Window):
    def __init__(self, monitor, cfg, screens=None):
        super().__init__()
        self.set_decorated(False)
        self.add_css_class('spark-wallpaper')
        layer.setup(self, 'background', ('top', 'bottom', 'left', 'right'), 'spark-wallpaper',
                    monitor, exclusive=-1)
        geometry = monitor.get_geometry()
        self.set_default_size(geometry.width, geometry.height)
        self.screens = screens or screen_sizes([monitor])
        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.set_child(self.picture)
        self.apply(cfg)

    def apply(self, cfg):
        mode = cfg['wallpaper_mode']
        self.picture.set_content_fit(FIT.get(mode, Gtk.ContentFit.COVER))
        self.picture.set_paintable(texture_for(config.wallpaper_file(cfg), self.screens, mode))
