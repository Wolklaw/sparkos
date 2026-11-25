"""The desktop: one background-layer window per monitor showing the wallpaper. No icons."""

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk  # noqa: E402

from . import config, layer  # noqa: E402

FIT = {
    'fill': Gtk.ContentFit.COVER,
    'fit': Gtk.ContentFit.CONTAIN,
    'stretch': Gtk.ContentFit.FILL,
    'center': Gtk.ContentFit.SCALE_DOWN,
}


class Wallpaper(Gtk.Window):
    def __init__(self, monitor, cfg):
        super().__init__()
        self.set_decorated(False)
        self.add_css_class('spark-wallpaper')
        layer.setup(self, 'background', ('top', 'bottom', 'left', 'right'), 'spark-wallpaper',
                    monitor, exclusive=-1)
        geometry = monitor.get_geometry()
        self.set_default_size(geometry.width, geometry.height)
        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.set_child(self.picture)
        self.apply(cfg)

    def apply(self, cfg):
        path = config.wallpaper_file(cfg)
        self.picture.set_content_fit(FIT.get(cfg['wallpaper_mode'], Gtk.ContentFit.COVER))
        self.picture.set_filename(path or None)
