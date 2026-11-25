"""Volume and brightness: the volume keys' actions and the on-screen display.

Volume goes through PipeWire's wpctl (the same server Spark Audio drives). Brightness belongs to
powerdevil, which the Spark session runs for the screen-off and sleep timers and the power
button: it takes the brightness keys, drives every monitor (backlight or DDC) and reports each
change to org.kde.plasmashell /org/kde/osdService, which the shell answers with this display."""

import logging
import re

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import layer  # noqa: E402
from .strings import tr  # noqa: E402

log = logging.getLogger('spark-shell')
STEP = 5


def parse_wpctl_volume(text: str):
    """'Volume: 0.45 [MUTED]' -> (0.45, True)."""
    m = re.search(r'Volume:\s*([0-9.]+)', text or '')
    if not m:
        return None
    return float(m.group(1)), '[MUTED]' in text


def _run(argv, callback):
    try:
        proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE |
                                  Gio.SubprocessFlags.STDERR_SILENCE)
    except GLib.Error:
        callback(None)
        return

    def done(p, res):
        try:
            ok, out, _ = p.communicate_utf8_finish(res)
        except GLib.Error:
            callback(None)
            return
        callback(out if ok and p.get_exit_status() == 0 else None)
    proc.communicate_utf8_async(None, None, done)


# What powerdevil calls on org.kde.plasmashell (Plasma's osdService). Only the brightness calls
# are answered; plasma-pa's and KWin's calls never come, since the shell does volume itself.
OSD_SERVICE_XML = """
<node>
  <interface name="org.kde.osdService">
    <method name="brightnessChanged"><arg type="i" name="percent" direction="in"/></method>
    <method name="screenBrightnessChanged">
      <arg type="i" name="percent" direction="in"/>
      <arg type="(iiii)" name="screenRect" direction="in"/>
    </method>
    <method name="keyboardBrightnessChanged"><arg type="i" name="percent" direction="in"/></method>
    <method name="hide"/>
  </interface>
</node>
"""


def osd_service_call(osd, method, args):
    """One org.kde.osdService call -> the Spark display. Percent is 0-100."""
    if method in ('brightnessChanged', 'screenBrightnessChanged'):
        osd.show_level('brightness', max(0, min(100, int(args[0]))) / 100)
    elif method == 'keyboardBrightnessChanged':
        osd.show_level('keyboard', max(0, min(100, int(args[0]))) / 100)
    elif method == 'hide':
        osd.hide_now()


class Osd(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_decorated(False)
        self.add_css_class('spark-transparent')
        layer.setup(self, 'overlay', ('bottom',), 'spark-osd', margins={'bottom': 90})
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class('spark-osd')
        box.set_size_request(260, -1)
        self.title = Gtk.Label(xalign=0)
        self.title.add_css_class('spark-label')
        self.bar = Gtk.ProgressBar()
        box.append(self.title)
        box.append(self.bar)
        self.box = box
        self.set_child(box)
        self._timer = 0
        self.last = None           # [kind, level] last shown, for the state call (tests)

    def show_level(self, kind, fraction, muted=False):
        self.last = [kind, round(fraction, 2)]
        names = {'volume': tr('volume'), 'brightness': tr('brightness'),
                 'keyboard': tr('keyboard')}
        text = names.get(kind, kind)
        if muted:
            text += '  ' + tr('muted')
        self.title.set_text(text)
        self.bar.set_fraction(max(0.0, min(1.0, fraction)))
        if muted:
            self.box.add_css_class('muted')
        else:
            self.box.remove_css_class('muted')
        self.present()
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(1600, self._hide)

    def hide_now(self):
        if self._timer:
            GLib.source_remove(self._timer)
        self._hide()

    def _hide(self):
        self._timer = 0
        self.set_visible(False)
        return False


class Controls:
    """Runs the key actions and tells the OSD."""

    def __init__(self, osd, conn):
        self.osd = osd
        self.conn = conn

    def key(self, name):
        if name == 'osd-test':          # shows the display with no audio or backlight (tests)
            self.osd.show_level('volume', 0.6)
            return
        if name.startswith('volume') or name == 'mute':
            self._volume(name)

    # volume ------------------------------------------------------------------------------
    def _volume(self, name):
        sink = '@DEFAULT_AUDIO_SINK@'
        if name == 'mute':
            argv = ['wpctl', 'set-mute', sink, 'toggle']
        elif name == 'volume-up':
            argv = ['wpctl', 'set-volume', '-l', '1.0', sink, '%d%%+' % STEP]
        else:
            argv = ['wpctl', 'set-volume', sink, '%d%%-' % STEP]
        _run(argv, lambda _out: _run(['wpctl', 'get-volume', sink], self._volume_shown))

    def _volume_shown(self, out):
        parsed = parse_wpctl_volume(out)
        if parsed:
            self.osd.show_level('volume', parsed[0], parsed[1])
